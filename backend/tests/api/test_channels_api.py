from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from tests.api.conftest import dev_login

from sportintel.composition import channel_feed

pytestmark = pytest.mark.integration
PAGE = Path(__file__).resolve().parents[2].parent / "fixtures/sources/telegram/channel_page.html"
CH = {"name": "Main", "tg_chat_id": "-1001234567890", "cron": "0 9,18 * * *", "active": False}


async def _channel(c, **kw):  # type: ignore[no-untyped-def]
    me = await dev_login(c, "admin@x.com", "admin")
    h = {"X-CSRF-Token": me["csrf_token"]}
    r = await c.post("/api/v1/channels", json={**CH, **kw}, headers=h)
    assert r.status_code == 201, r.text
    assert r.json()["language"] == "en"  # язык постов по умолчанию
    return r.json()


async def test_schedule_lists_next_runs_without_sending(make_app, client_for) -> None:  # type: ignore[no-untyped-def]
    c = client_for(make_app())
    ch = await _channel(c)
    r = await c.get(f"/api/v1/channels/{ch['id']}/schedule")
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["next_runs"]) == 71  # пять недель вперёд: «сейчас» + 35 дней × 2
    hours = {t[11:16] for t in body["next_runs"][1:]}
    assert hours == {"09:00", "18:00"}
    assert (body["queue"], body["posts"], body["skipped"]) == ([], [], {})


async def test_pin_needs_future_time_and_a_ready_post(make_app, client_for) -> None:  # type: ignore[no-untyped-def]
    c = client_for(make_app())
    ch = await _channel(c)
    h = {"X-CSRF-Token": (await dev_login(c, "admin@x.com", "admin"))["csrf_token"]}
    url = f"/api/v1/channels/{ch['id']}/pins/0192f6a1-0000-7000-8000-0000000000e1"
    past = await c.put(url, json={"publish_at": "2020-01-01T10:00:00Z"}, headers=h)
    assert past.status_code == 422
    assert past.json()["errors"][0]["code"] == "out_of_range"
    soon = (datetime.now(UTC) + timedelta(hours=2)).isoformat()  # noqa: TID251 — время сервера
    not_ready = await c.put(url, json={"publish_at": soon}, headers=h)
    assert not_ready.json()["errors"][0]["code"] == "not_ready"
    assert (await c.delete(url, headers=h)).status_code == 204


async def test_feed_private_chat_falls_back_to_journal(make_app, client_for) -> None:  # type: ignore[no-untyped-def]
    c = client_for(make_app(telegram_bot_token=None))
    ch = await _channel(c)
    r = await c.get(f"/api/v1/channels/{ch['id']}/feed")
    assert (r.json()["live"], r.json()["reason"]) == (False, "private_chat_id")


async def test_feed_reads_public_channel(make_app, client_for, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async def fake_fetch(username: str) -> bytes:
        assert username == "igaming_news"
        return PAGE.read_bytes()

    monkeypatch.setattr(channel_feed, "fetch_public_channel", fake_fetch)
    c = client_for(make_app())
    ch = await _channel(c, tg_chat_id="@igaming_news")
    body = (await c.get(f"/api/v1/channels/{ch['id']}/feed")).json()
    assert body["live"] is True
    assert len(body["items"]) == 12  # и пересланный пост только с медиа
    last = body["items"][-1]
    assert last["url"] == "https://t.me/igaming_news/11547"
    assert '<a href="https://www.inkl.com/' in last["html"]  # разметка поста сохранена
    assert (last["views"], last["reactions"][0]) == ("932", {"emoji": "🤣", "count": "7"})
    album = next(p for p in body["items"] if len(p["photos"]) > 1)
    assert len(album["photos"]) == 9
    assert any(p["forwarded_from"] == "01.tech" for p in body["items"])
    assert (body["title"], body["subscribers"]) == ("iGamingNews", "20.8K")
    assert body["avatar_url"].startswith("https://cdn4.telesco.pe/")


async def test_feed_of_public_channel_by_numeric_id(make_app, client_for, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Канал подключён по -100… id, но публичный: username узнаём у бота, ленту читаем с t.me."""

    async def fake_username(token: str, chat_id: str) -> str:
        assert (token, chat_id) == ("t0ken", "-1001234567890")
        return "igaming_news"

    async def fake_fetch(username: str) -> bytes:
        assert username == "igaming_news"
        return PAGE.read_bytes()

    monkeypatch.setattr(channel_feed, "channel_username", fake_username)
    monkeypatch.setattr(channel_feed, "fetch_public_channel", fake_fetch)
    c = client_for(make_app(telegram_bot_token="t0ken"))
    ch = await _channel(c)
    body = (await c.get(f"/api/v1/channels/{ch['id']}/feed")).json()
    assert (body["live"], body["username"], len(body["items"])) == (True, "igaming_news", 12)


async def test_check_does_not_post_and_explains_missing_rights(
    make_app, client_for, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    from sportintel.modules.editorial.api import channels_router

    async def fake_check(token: str, chat_id: str) -> dict[str, object]:
        return {
            "title": "Main",
            "username": None,
            "bot_username": "si_bot",
            "problem": "cannot_post",
        }

    monkeypatch.setattr(channels_router, "check_channel", fake_check)
    c = client_for(make_app(telegram_bot_token="t0ken"))
    ch = await _channel(c)
    h = {"X-CSRF-Token": (await dev_login(c, "admin@x.com", "admin"))["csrf_token"]}
    r = await c.post(f"/api/v1/channels/{ch['id']}:check", headers=h)
    assert r.json()["problem"] == "cannot_post"


async def test_send_now_needs_a_ready_post(make_app, client_for, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("FLAG_TELEGRAM_PUBLISH", "true")
    c = client_for(make_app(telegram_bot_token="t0ken"))
    ch = await _channel(c)
    h = {"X-CSRF-Token": (await dev_login(c, "admin@x.com", "admin"))["csrf_token"]}
    url = f"/api/v1/channels/{ch['id']}/posts/0192f6a1-0000-7000-8000-0000000000e1:send"
    r = await c.post(url, headers=h)
    assert r.json()["errors"][0]["code"] == "not_ready"
