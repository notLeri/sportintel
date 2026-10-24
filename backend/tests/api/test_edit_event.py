import pytest
from sqlalchemy import text
from tests.api.conftest import dev_login
from tests.factories import make_article, make_entity, make_event, make_source

from sportintel.modules.events.application.refresh_event import refresh_event
from sportintel.modules.events.domain.values import ArticleLink, AttachMethod
from sportintel.modules.events.jobs import repo_for
from sportintel.modules.taxonomy.domain.values import EntityKind
from sportintel.platform.clock import SystemClock
from sportintel.platform.db import Database

pytestmark = pytest.mark.integration


async def setup(make_app, client_for, db: Database):  # type: ignore[no-untyped-def]
    async with db.uow() as u:
        s = await make_source(u)
        a = await make_article(u, s, title="Lesão de Pedro", lead="Pedro sai do jogo.")
        ev = await make_event(u, [a])
        team = await make_entity(u, "Time Edit")
        comp = await make_entity(u, "Copa Edit", kind=EntityKind.COMPETITION)
    c = client_for(make_app())
    me = await dev_login(c, "edit@corp.com", "researcher")
    return c, {"X-CSRF-Token": me["csrf_token"]}, ev, team, comp, s


async def patch(c, h, ev_id, version, body):  # type: ignore[no-untyped-def]
    return await c.patch(
        f"/api/v1/events/{ev_id}", json=body, headers={**h, "If-Match": f'"{version}"'}
    )


async def test_edit_fields_validation_and_412(make_app, client_for, db: Database) -> None:  # type: ignore[no-untyped-def]
    c, h, ev, team, comp, _ = await setup(make_app, client_for, db)
    r = await patch(
        c,
        h,
        ev.id,
        1,
        {
            "title": "Título editado",
            "summary": "Resumo [1] humano [7].",
            "sport_id": "football",
            "competition_id": str(comp.id),
            "team_ids": [str(team.id)],
        },
    )
    assert r.status_code == 200, r.text
    b = r.json()
    assert (
        b["title"],
        b["summary"]["origin"],
        b["sport_id"],
        b["competition"]["name"],
        b["version"],
    ) == ("Título editado", "human", "football", "Copa Edit", 2)
    assert set(b["manual_overrides"]) == {"title", "summary", "sport", "competition", "entities"}
    assert b["teams"] == [{"id": str(team.id), "name": "Time Edit"}]
    assert (await patch(c, h, ev.id, 1, {"title": "x"})).status_code == 412
    assert (await patch(c, h, ev.id, 2, {})).json()["code"] == "common.validation_failed"
    assert (await patch(c, h, ev.id, 2, {"team_ids": [str(comp.id)]})).status_code == 422
    assert (await patch(c, h, ev.id, 2, {"sport_id": "curling"})).status_code == 422
    same = await patch(c, h, ev.id, 2, {"title": "Título editado"})
    assert same.json()["version"] == 2  # без изменений версия не растёт
    async with db.uow() as u:
        n = (
            await u.session.execute(
                text(
                    "SELECT count(*) FROM audit.audit_log WHERE target_id=:i AND action='event.edited'"
                ),
                {"i": str(ev.id)},
            )
        ).scalar()
    assert n == 1


async def test_summary_survives_refresh_and_regenerate(make_app, client_for, db: Database) -> None:  # type: ignore[no-untyped-def]
    c, h, ev, _, _, s = await setup(make_app, client_for, db)
    assert (await patch(c, h, ev.id, 1, {"summary": "Meu resumo."})).status_code == 200
    async with db.uow() as u:
        a2 = await make_article(u, s, title="Outra matéria")
        got = await repo_for(u).get(ev.id)
        assert got
        got.attach(ArticleLink(a2.id, got.first_seen_at, 0.9, AttachMethod.AUTO), got.first_seen_at)
        await repo_for(u).save(got, got.version)
    await refresh_event(db, ev.id, SystemClock(), repo_for)
    d = (await c.get(f"/api/v1/events/{ev.id}")).json()
    assert (d["summary"]["text"], d["has_updates_since_edit"]) == ("Meu resumo.", True)
    r = await c.post(
        f"/api/v1/events/{ev.id}/summary:regenerate", headers={**h, "If-Match": f'"{d["version"]}"'}
    )
    assert r.status_code == 200, r.text
    assert "summary" not in r.json()["manual_overrides"]
    assert r.json()["summary"]["origin"] == "source"
