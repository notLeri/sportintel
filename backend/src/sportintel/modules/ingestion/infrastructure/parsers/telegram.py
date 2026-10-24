"""Профиль публичного Telegram-канала: веб-превью https://t.me/s/<канал> (без API и ключей).

Список — сообщения с текстом; заголовок — первая строка, лид — весь текст. Страница поста
(t.me/<канал>/<id>) текста для trafilatura не содержит: текст берётся из og:description.
"""

import re
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser

from sportintel.modules.ingestion.domain.feed_item import FeedItem
from sportintel.modules.ingestion.infrastructure.extractor import ExtractedPage
from sportintel.modules.ingestion.infrastructure.feeds import parse_date

TITLE_MAX = 200
_OG_DESC = re.compile(rb'<meta property="og:description" content="([^"]*)"')
_BG_URL = re.compile(r"background-image:url\('([^']+)'\)")


@dataclass
class _Msg:
    post: str
    lines: list[str]
    published: str | None = None
    image: str | None = None


class _Channel(HTMLParser):
    """stdlib-парсер: скрипты не исполняются; вложенность div считается для границ текста."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.messages: list[_Msg] = []
        self._text_depth = 0  # >0 — внутри tgme_widget_message_text
        self._skip_depth = 0  # >0 — внутри <i class="emoji"> (картинка-дубль эмодзи в <b>)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        cls = a.get("class") or ""
        if tag == "div" and a.get("data-post") and "tgme_widget_message" in cls.split():
            # «Канал создан», «Фото обновлено» — служебные, не новости
            post = "" if "service_message" in cls.split() else a["data-post"] or ""
            self.messages.append(_Msg(post=post, lines=[""]))
            return
        if not self.messages:
            return
        msg = self.messages[-1]
        if self._text_depth:
            if tag == "div":
                self._text_depth += 1
            elif tag == "br":
                msg.lines.append("")
            return
        if tag == "div" and "tgme_widget_message_text" in cls.split():
            self._text_depth = 1
        elif tag == "time" and a.get("datetime") and msg.published is None:
            msg.published = a["datetime"]
        elif tag == "a" and "tgme_widget_message_photo_wrap" in cls and msg.image is None:
            m = _BG_URL.search(a.get("style") or "")
            msg.image = m.group(1) if m else None

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if self._text_depth and tag == "div":
            self._text_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._text_depth:
            self.messages[-1].lines[-1] += data


@dataclass(frozen=True)
class TelegramProfile:
    name: str = "telegram"
    empty_list_is_error: bool = (
        True  # пустая страница канала — вероятно, канал закрыт или переименован
    )

    def list_items(self, body: bytes, content_type: str, base_url: str) -> list[FeedItem]:
        parser = _Channel()
        parser.feed(body.decode("utf-8", errors="replace"))
        items = []
        for m in parser.messages:
            lines = [" ".join(line.split()) for line in m.lines]
            lines = [line for line in lines if line]
            if not lines or "/" not in m.post:
                continue  # только медиа без подписи — заголовка нет
            title = lines[0] if len(lines[0]) <= TITLE_MAX else lines[0][: TITLE_MAX - 1] + "…"
            items.append(
                FeedItem(
                    url=f"https://t.me/{m.post}",
                    title=title,
                    summary="\n".join(lines),
                    published_at=parse_date(m.published),
                    image_url=m.image,
                    author=None,
                )
            )
        return items

    def postprocess(self, page: ExtractedPage, html: bytes, url: str) -> ExtractedPage:
        m = _OG_DESC.search(html)
        text = unescape(m.group(1).decode("utf-8", errors="replace")).strip() if m else ""
        if not text or page.text:
            return page
        return ExtractedPage(
            title=page.title,
            text=text,
            description=page.description,
            published_at=page.published_at,
            image_url=page.image_url,
            author=page.author,
            language=page.language,
            canonical_url=page.canonical_url,
        )


TELEGRAM = TelegramProfile()
