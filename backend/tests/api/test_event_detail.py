import pytest
from sqlalchemy import text
from tests.api.conftest import dev_login
from tests.factories import make_article, make_entity, make_event, make_source

from sportintel.modules.events.domain.values import RelationKind
from sportintel.modules.events.infrastructure.repository import SqlEventRepository
from sportintel.modules.taxonomy.domain.values import EntityKind
from sportintel.platform.db import Database

pytestmark = pytest.mark.integration


async def test_detail_shape_etag_include_and_source_down(
    make_app, client_for, db: Database
) -> None:  # type: ignore[no-untyped-def]
    async with db.uow() as u:
        s = await make_source(u, domain="det.example.com")
        await u.session.execute(
            text("UPDATE sources.sources SET health='down' WHERE id=:i"), {"i": s.id}
        )
        a1, a2 = (
            await make_article(u, s, title="Primeira"),
            await make_article(u, s, title="Segunda"),
        )
        team, player = (
            await make_entity(u, "Time Det"),
            await make_entity(u, "Jogador Det", kind=EntityKind.PLAYER),
        )
        ev = await make_event(u, [a1, a2], summary="Resumo", source_ids=[s.id])
        other = await make_event(u, [await make_article(u, s)], title="Relacionado")
        repo = SqlEventRepository(u.session)
        await repo.replace_entities(
            ev.id, [(team.id, "team", 2, False), (player.id, "player", 1, False)]
        )
        await repo.replace_relations(ev.id, RelationKind.RELATED, [(other.id, 2.0)])
    c = client_for(make_app())
    await dev_login(c, "detail@corp.com", "researcher")
    r = await c.get(f"/api/v1/events/{ev.id}")
    assert r.status_code == 200, r.text
    assert r.headers["ETag"] == '"1"'
    body = r.json()
    assert [a["title"] for a in body["articles"]] == ["Primeira", "Segunda"]
    assert body["articles"][0]["source"]["health"] == "down"
    assert body["teams"] == [{"id": str(team.id), "name": "Time Det"}]
    assert [p["name"] for p in body["players"]] == ["Jogador Det"]
    assert body["related"][0]["title"] == "Relacionado"
    assert body["summary"]["text"] == "Resumo"
    assert body["draft"] is None
    slim = (await c.get(f"/api/v1/events/{ev.id}", params={"include": "conflicts"})).json()
    assert (slim["articles"], slim["related"], slim["conflicts"]) == (None, None, [])
    assert (await c.get(f"/api/v1/events/{ev.id}", params={"include": "nope"})).status_code == 422
    assert (await c.get("/api/v1/events/00000000-0000-0000-0000-000000000000")).status_code == 404


async def test_opened_event_is_translated_with_its_source_cards(
    make_app, client_for, db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    from datetime import UTC, datetime

    from sportintel.modules.editorial.application.translate import translate_event
    from sportintel.modules.editorial.jobs import translations_cache
    from sportintel.modules.events.api import router as events_router
    from sportintel.platform.clock import FrozenClock
    from sportintel.platform.llm import FakeProvider

    async with db.uow() as u:
        pt, ru = await make_source(u), await make_source(u)
        await u.session.execute(
            text("UPDATE sources.sources SET language='ru' WHERE id=:i"), {"i": ru.id}
        )
        a_pt = await make_article(u, pt, title="Vasco vence")
        a_ru = await make_article(u, ru, title="Васко победил")
        ev = await make_event(u, [a_pt, a_ru], title="Vasco vence", source_ids=[pt.id, ru.id])
    queued: list[object] = []

    async def _record(request: object, event_id: object) -> None:
        queued.append(event_id)

    monkeypatch.setattr(events_router, "_translate_now", _record)
    c = client_for(make_app(ai_provider="fake"))
    await dev_login(c, "translate@corp.com", "researcher")
    body = (await c.get(f"/api/v1/events/{ev.id}")).json()
    assert body["translation_pending"] is True
    assert queued == [ev.id]
    assert body["articles"][0]["source"]["language"] == body["original_language"]

    llm = FakeProvider({"EventText": {"title": "«Васко» победил", "summary": ""}})
    clock = FrozenClock(datetime(2026, 10, 11, tzinfo=UTC))
    assert await translate_event(db, translations_cache, llm, ev.id, "ru", clock)
    assert len(llm.calls) == 1  # статья на русском — без модели, заголовок pt — из кеша события

    body = (await c.get(f"/api/v1/events/{ev.id}")).json()
    assert body["translation_pending"] is False
    assert {a["title"]: a["translation"]["title"] for a in body["articles"]} == {
        "Vasco vence": "«Васко» победил",
        "Васко победил": "Васко победил",
    }
    assert not await translate_event(db, translations_cache, llm, ev.id, "ru", clock)
