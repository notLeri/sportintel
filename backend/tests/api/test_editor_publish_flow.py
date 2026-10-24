"""Сквозной путь редактора через API: событие → черновик → «Готово» → автопостинг → Telegram.

Главное правило: в канал уходит ровно тот текст, который редактор утвердил статусом «Готово»,
и только на языке канала. Любая новая версия (правка, перегенерация, перевод) снимает утверждение.
"""

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from tests.api.conftest import dev_login
from tests.factories import make_article, make_event, make_source

from sportintel.modules.editorial.api import channels_router
from sportintel.modules.editorial.application import translate
from sportintel.modules.events.domain.values import EventStatus
from sportintel.modules.sources.domain.values import SourceTier
from sportintel.platform.db import Database

pytestmark = pytest.mark.integration


class FakeTelegram:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, chat_id: str, html: str) -> int:
        self.sent.append(html)
        return len(self.sent)


async def _world(make_app, client_for, db: Database, monkeypatch, post_lang: str):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("FLAG_TELEGRAM_PUBLISH", "true")
    tg = FakeTelegram()
    monkeypatch.setattr(channels_router, "_publisher", lambda request: tg)
    app = make_app(telegram_bot_token="t0ken")
    now = app.state.clock.now()
    async with db.uow() as u:
        s = await make_source(u, tier=SourceTier.A, language=post_lang)
        a = await make_article(u, s, title="Pedro é cortado", lead="Exames confirmaram a lesão.")
        ev = await make_event(u, [a], status=EventStatus.NEW, sport_id="football", now=now)
        await u.session.execute(
            text("UPDATE events.events SET relevance='HIGH' WHERE id=:i"),
            {"i": ev.id},
        )
    researcher, editor, admin = client_for(app), client_for(app), client_for(app)
    hr = {
        "X-CSRF-Token": (await dev_login(researcher, "flow-r@corp.com", "researcher"))["csrf_token"]
    }
    he = {"X-CSRF-Token": (await dev_login(editor, "flow-e@corp.com", "editor"))["csrf_token"]}
    ha = {"X-CSRF-Token": (await dev_login(admin, "flow-a@corp.com", "admin"))["csrf_token"]}
    ch = await admin.post(
        "/api/v1/channels",
        json={"name": "Main", "tg_chat_id": "-1001234567890", "language": "en", "active": True},
        headers=ha,
    )
    assert ch.status_code == 201, ch.text
    return tg, ev, ch.json(), (researcher, hr), (editor, he), (admin, ha)


async def _move(c, h, event_id, to: str) -> None:  # type: ignore[no-untyped-def]
    e = (await c.get(f"/api/v1/events/{event_id}")).json()
    r = await c.post(
        f"/api/v1/events/{event_id}/transitions",
        json={"to": to},
        headers={**h, "If-Match": f'"{e["version"]}"'},
    )
    assert r.status_code == 200, r.text


async def _save(c, h, draft_id, body: str):  # type: ignore[no-untyped-def]
    d = (await c.get(f"/api/v1/drafts/{draft_id}")).json()
    r = await c.patch(
        f"/api/v1/drafts/{draft_id}",
        json={"body_tg_html": body},
        headers={**h, "If-Match": f'"{d["version"]}"'},
    )
    assert r.status_code == 200, r.text
    return r.json()


async def test_editor_approves_and_exactly_that_text_is_published(  # type: ignore[no-untyped-def]
    make_app, client_for, db: Database, monkeypatch
) -> None:
    tg, ev, ch, (rc, hr), (ec, he), (ac, ha) = await _world(
        make_app, client_for, db, monkeypatch, "en"
    )
    # исследователь отбирает событие и делает черновик
    await _move(rc, hr, ev.id, "SELECTED")
    d = (
        await rc.post(
            f"/api/v1/events/{ev.id}/drafts",
            json={},
            headers={**hr, "Idempotency-Key": str(uuid.uuid4())},
        )
    ).json()
    assert d["current"]["lang"] == "en"  # шаблон — язык статьи, а не настройка
    assert d["channels"] == [{"name": "Main", "language": "en", "active": True, "blocked": None}]
    # событие ниже порога важности канала: редактор видит это до «Готово»
    async with db.uow() as u:
        await u.session.execute(
            text("UPDATE events.events SET relevance='MEDIUM' WHERE id=:i"), {"i": ev.id}
        )
    low = (await ec.get(f"/api/v1/drafts/{d['id']}")).json()
    assert low["channels"][0]["blocked"] == "filters"
    async with db.uow() as u:
        await u.session.execute(
            text("UPDATE events.events SET relevance='HIGH' WHERE id=:i"), {"i": ev.id}
        )
    # редактор правит и утверждает
    await _save(ec, he, d["id"], "<b>Pedro is out</b>")
    await _move(ec, he, ev.id, "READY")
    sched = (await ac.get(f"/api/v1/channels/{ch['id']}/schedule")).json()
    assert [q["body_tg_html"] for q in sched["queue"]] == ["<b>Pedro is out</b>"]

    # правка после «Готово» снимает утверждение: в канал ничего не уходит
    await _save(ec, he, d["id"], "<b>Pedro is out — unapproved edit</b>")
    assert (await ec.get(f"/api/v1/events/{ev.id}")).json()["status"] == "DRAFT"
    run = (await ac.post(f"/api/v1/channels/{ch['id']}:run", headers=ha)).json()
    assert (run["sent"], tg.sent) == (0, [])

    # повторное утверждение — уходит ровно утверждённый текст, один раз
    await _move(ec, he, ev.id, "READY")
    run = (await ac.post(f"/api/v1/channels/{ch['id']}:run", headers=ha)).json()
    assert tg.sent == ["<b>Pedro is out — unapproved edit</b>"]
    assert (await ec.get(f"/api/v1/events/{ev.id}")).json()["status"] == "PUBLISHED"
    again = (await ac.post(f"/api/v1/channels/{ch['id']}:run", headers=ha)).json()
    assert (again["sent"], len(tg.sent)) == (0, 1)


async def test_post_in_another_language_waits_and_translation_needs_new_approval(  # type: ignore[no-untyped-def]
    make_app, client_for, db: Database, monkeypatch
) -> None:
    """Сценарий бага: шаблон на языке статьи (ru), канал en. Не уходит ничего, пока редактор
    не переведёт пост и не утвердит перевод заново."""

    async def fake_translator(db, settings):  # type: ignore[no-untyped-def]
        return SimpleNamespace(model="fake")

    async def fake_translate(db, cache, llm, body, lang, html=False):  # type: ignore[no-untyped-def]
        return "<b>Pedro is out (translated)</b>"

    monkeypatch.setattr(translate, "translator_for", fake_translator)
    monkeypatch.setattr(translate, "translate", fake_translate)
    tg, ev, ch, (rc, hr), (ec, he), (ac, ha) = await _world(
        make_app, client_for, db, monkeypatch, "ru"
    )
    await _move(rc, hr, ev.id, "SELECTED")
    d = (
        await rc.post(
            f"/api/v1/events/{ev.id}/drafts",
            json={},
            headers={**hr, "Idempotency-Key": str(uuid.uuid4())},
        )
    ).json()
    assert d["current"]["lang"] == "ru"  # раньше здесь была ложная метка en
    assert d["channels"][0]["blocked"] == "language"
    await _move(ec, he, ev.id, "READY")
    sched = (await ac.get(f"/api/v1/channels/{ch['id']}/schedule")).json()
    assert (sched["queue"], sched["skipped"]) == ([], {"no_post_in_language": 1})
    run = (await ac.post(f"/api/v1/channels/{ch['id']}:run", headers=ha)).json()
    assert (run["sent"], tg.sent) == (0, [])

    # перевод — новая версия: утверждение снимается, перевод надо утвердить
    tr = await ec.post(f"/api/v1/drafts/{d['id']}:translate", json={"lang": "en"}, headers=he)
    assert tr.status_code == 200, tr.text
    assert (await ec.get(f"/api/v1/events/{ev.id}")).json()["status"] == "DRAFT"
    await _move(ec, he, ev.id, "READY")
    await ac.post(f"/api/v1/channels/{ch['id']}:run", headers=ha)
    assert tg.sent == ["<b>Pedro is out (translated)</b>"]
