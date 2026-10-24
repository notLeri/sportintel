import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from tests.api.conftest import dev_login
from tests.factories import make_article, make_source

from sportintel.modules.intelligence.infrastructure.repository import SqlEnrichmentRepository
from sportintel.platform.db import Database

pytestmark = pytest.mark.integration


async def admin(make_app, client_for):  # type: ignore[no-untyped-def]
    c = client_for(make_app())
    me = await dev_login(c, "tax-admin@corp.com", "admin")
    return c, {"X-CSRF-Token": me["csrf_token"]}


async def test_entities_aliases_and_sports(make_app, client_for, db: Database) -> None:  # type: ignore[no-untyped-def]
    c, h = await admin(make_app, client_for)
    r = await c.post(
        "/api/v1/taxonomy/entities",
        json={
            "kind": "player",
            "sport_id": "football",
            "canonical_name": "Gabriel Barbosa Adm",
            "aliases": ["Gabigol Adm"],
        },
        headers=h,
    )
    assert r.status_code == 201, r.text
    e = r.json()
    assert set(e["aliases"]) == {"Gabriel Barbosa Adm", "Gabigol Adm"}
    dup = await c.post(
        "/api/v1/taxonomy/entities",
        json={"kind": "player", "sport_id": "football", "canonical_name": "gabriel barbosa adm"},
        headers=h,
    )
    assert (dup.status_code, dup.json()["errors"][0]["field"]) == (409, "canonical_name")
    assert (
        len(
            (
                await c.post(
                    f"/api/v1/taxonomy/entities/{e['id']}/aliases",
                    json={"alias": "Gabi Adm"},
                    headers=h,
                )
            ).json()["aliases"]
        )
        == 3
    )
    assert (
        await c.post(
            f"/api/v1/taxonomy/entities/{e['id']}/aliases", json={"alias": "Gabi Adm"}, headers=h
        )
    ).status_code == 200
    assert (
        await c.delete(
            f"/api/v1/taxonomy/entities/{e['id']}/aliases/gabriel barbosa adm", headers=h
        )
    ).status_code == 422
    assert (
        len(
            (
                await c.delete(f"/api/v1/taxonomy/entities/{e['id']}/aliases/gabi adm", headers=h)
            ).json()["aliases"]
        )
        == 2
    )
    p = await c.patch(
        f"/api/v1/taxonomy/entities/{e['id']}",
        json={"priority": 2},
        headers={**h, "If-Match": f'"{e["version"]}"'},
    )
    assert (p.status_code, p.json()["priority"], p.json()["version"]) == (200, 2, 2)
    assert (
        await c.patch(
            f"/api/v1/taxonomy/entities/{e['id']}",
            json={"priority": 1},
            headers={**h, "If-Match": '"1"'},
        )
    ).status_code == 412
    found = (await c.get("/api/v1/taxonomy/entities/admin", params={"q": "gabigol adm"})).json()[
        "items"
    ]
    assert [x["id"] for x in found] == [e["id"]]
    s = await c.post(
        "/api/v1/taxonomy/sports",
        json={
            "id": "handball",
            "name_i18n": {"pt-BR": "Handebol", "en": "Handball", "ru": "Гандбол"},
            "sort": 70,
        },
        headers=h,
    )
    assert s.status_code == 201
    assert (
        await c.patch("/api/v1/taxonomy/sports/handball", json={"active": False}, headers=h)
    ).json()["active"] is False
    async with db.uow() as u:
        n = (
            await u.session.execute(
                text("SELECT count(*) FROM audit.audit_log WHERE action LIKE 'taxonomy.%'")
            )
        ).scalar()
    assert n >= 6


async def test_unlinked_resolve_and_relink(make_app, client_for, db: Database) -> None:  # type: ignore[no-untyped-def]
    now = datetime(2026, 10, 9, 12, tzinfo=UTC)
    async with db.uow() as u:
        await u.session.execute(
            text(
                "INSERT INTO taxonomy.unlinked_mentions (mention_norm, kind, sport_key, sport_id, mention, occurrences, first_seen_at, last_seen_at)"
                " VALUES ('joaozinho teste', 'player', 'football', 'football', 'Joãozinho Teste', 5, :t, :t)"
            ),
            {"t": now},
        )
        a = await make_article(u, await make_source(u))
        await u.session.execute(
            text(
                "INSERT INTO intelligence.article_enrichments (article_id, relevance, prompt_version, enriched_at, raw_entities)"
                " VALUES (:i, 'LOW', 'rules/v2', :t, CAST(:r AS jsonb))"
            ),
            {
                "i": a.id,
                "t": now,
                "r": json.dumps(
                    [{"mention": "Joãozinho Teste", "kind": "player", "role": "subject"}]
                ),
            },
        )
    c, h = await admin(make_app, client_for)
    items = (await c.get("/api/v1/taxonomy/unlinked")).json()["items"]
    assert items[0]["mention_norm"] == "joaozinho teste"
    r = await c.post(
        "/api/v1/taxonomy/unlinked/joaozinho teste:resolve",
        json={"kind": "player", "sport_key": "football", "action": "create"},
        headers=h,
    )
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "resolved"
    async with db.uow() as u:
        hit, more = await SqlEnrichmentRepository(u.session).relink_batch(
            "joaozinho teste", r.json()["entity_id"], now - timedelta(days=30), None, 500
        )
        role = (
            await u.session.execute(
                text("SELECT role FROM intelligence.article_entities WHERE article_id=:a"),
                {"a": a.id},
            )
        ).scalar()
    assert (hit, more, role) == ([a.id], None, "subject")
