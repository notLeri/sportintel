"""Уведомления команды (BE-T4.13): Telegram-бот или, без токена, только лог."""

import re
import time
from typing import Any

import httpx
import structlog

_log = structlog.get_logger("sportintel.health")
TIMEOUT_S = 10.0


class TelegramNotifier:
    def __init__(self, bot_token: str | None, chat_id: str | None) -> None:
        self.bot_token, self.chat_id = bot_token, chat_id

    async def send(self, text: str) -> None:
        if not self.bot_token or not self.chat_id:
            _log.warning("health.alert", text=text)
            return
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            r = await client.post(
                f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )
            r.raise_for_status()


class PublishError(Exception):
    """Telegram отказал (нет прав, неверный chat_id): публикация помечается failed с описанием."""


class TelegramPublisher:
    """Публикация в каналы от имени бота TELEGRAM_BOT_TOKEN (фаза 6)."""

    def __init__(self, bot_token: str) -> None:
        self._token = bot_token

    async def send(self, chat_id: str, html: str) -> int:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            try:
                r = await client.post(
                    f"https://api.telegram.org/bot{self._token}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": html,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": True,
                    },
                )
            except httpx.HTTPError as e:
                raise PublishError(f"network: {e.__class__.__name__}") from e
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if r.status_code != 200 or not body.get("ok"):
            raise PublishError(str(body.get("description") or f"HTTP {r.status_code}"))
        return int(body["result"]["message_id"])


async def _bot_call(bot_token: str, method: str, **params: Any) -> Any:
    """Метод Bot API без побочных эффектов (getMe, getChat…): result или PublishError."""
    async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
        try:
            r = await client.get(f"https://api.telegram.org/bot{bot_token}/{method}", params=params)
        except httpx.HTTPError as e:
            raise PublishError(f"network: {e.__class__.__name__}") from e
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if not body.get("ok"):
        raise PublishError(str(body.get("description") or f"HTTP {r.status_code}"))
    return body["result"]


# ponytail: кэш в памяти процесса; переименование канала подхватится через час
_USERNAMES: dict[str, tuple[float, str | None]] = {}
USERNAME_TTL_S = 3600.0


async def channel_username(bot_token: str, chat_id: str) -> str | None:
    """@username канала по числовому id (getChat): у публичного канала он есть, у закрытого — нет."""
    hit = _USERNAMES.get(chat_id)
    if hit and time.monotonic() - hit[0] < USERNAME_TTL_S:
        return hit[1]
    username = (await _bot_call(bot_token, "getChat", chat_id=chat_id)).get("username")
    _USERNAMES[chat_id] = (time.monotonic(), username)
    return username


async def check_channel(bot_token: str, chat_id: str) -> dict[str, Any]:
    """Подключение без публикации: бот видит канал и может в нём публиковать?
    problem: None | not_admin | cannot_post. Ошибка Telegram (нет чата) — PublishError."""
    me = await _bot_call(bot_token, "getMe")
    chat = await _bot_call(bot_token, "getChat", chat_id=chat_id)
    member = await _bot_call(bot_token, "getChatMember", chat_id=chat_id, user_id=me["id"])
    status = member.get("status")
    problem = (
        None
        if status == "creator"
        or (status == "administrator" and member.get("can_post_messages", True))
        else "not_admin"
        if status != "administrator"
        else "cannot_post"
    )
    _USERNAMES[chat_id] = (time.monotonic(), chat.get("username"))
    return {
        "title": chat.get("title") or "",
        "username": chat.get("username"),
        "bot_username": me.get("username") or "",
        "problem": problem,
    }


_TG_USERNAME = re.compile(r"^[A-Za-z0-9_]{5,32}$")


async def fetch_public_channel(username: str) -> bytes:
    """Веб-превью публичного канала t.me/s/<username> (то, что видит подписчик). Хост фиксирован."""
    if not _TG_USERNAME.fullmatch(username):
        raise PublishError("invalid channel username")
    async with httpx.AsyncClient(timeout=TIMEOUT_S, follow_redirects=False) as client:
        try:
            r = await client.get(
                f"https://t.me/s/{username}", headers={"User-Agent": "Mozilla/5.0"}
            )
        except httpx.HTTPError as e:
            raise PublishError(f"network: {e.__class__.__name__}") from e
    if r.status_code != 200:
        raise PublishError(f"HTTP {r.status_code}")  # 302 на t.me/<name> — канал закрытый
    return r.content
