import uuid
from datetime import UTC, datetime

import pytest
from tests.api.conftest import dev_login
from tests.factories import make_article, make_event, make_source

from sportintel.modules.events.domain.values import EventStatus
from sportintel.modules.sources.domain.values import SourceTier
from sportintel.platform.db import Database

pytestmark = pytest.mark.integration


async def setup(
    make_app,
    client_for,
    db: Database,
    role: str = "researcher",
    status: EventStatus = EventStatus.SELECTED,
    articles: bool = True,
):  # type: ignore[no-untyped-def]
    async with db.uow() as u:
        s = await make_source(u, tier=SourceTier.A)
        arts = (
            [await make_article(u, s, title="Pedro é cortado", lead="Exames confirmaram a lesão.")]
            if articles
            else []
        )
        if arts:
            ev = await make_event(u, arts, status=status, sport_id="football")
        else:
            from sportintel.modules.events.domain.actor import SYSTEM
            from sportintel.modules.events.domain.event import Event
            from sportintel.modules.events.infrastructure.repository import SqlEventRepository
            from sportintel.platform.ids import new_id

            ev = Event.create_manual(
                new_id(),
                "Manual",
                None,
                None,
                None,
                SYSTEM,
                datetime(2026, 10, 9, 12, tzinfo=UTC),
            )
            ev.status = status
            await SqlEventRepository(u.session).add(ev)
    c = client_for(make_app())
    me = await dev_login(c, f"draft-{role}@corp.com", role)
    return c, {"X-CSRF-Token": me["csrf_token"]}, ev


def idem(h: dict[str, str]) -> dict[str, str]:
    return {**h, "Idempotency-Key": str(uuid.uuid4())}


async def test_template_draft_flow(make_app, client_for, db: Database) -> None:  # type: ignore[no-untyped-def]
    c, h, ev = await setup(make_app, client_for, db)
    r = await c.post(f"/api/v1/events/{ev.id}/drafts", json={}, headers=idem(h))
    assert r.status_code == 201, r.text
    d = r.json()
    cur = d["current"]
    assert (d["state"], cur["n"], cur["origin"], d["auto"]) == ("ready", 1, "template", False)
    assert cur["body_tg_html"].startswith("<b>⚽ Pedro é cortado</b>")
    assert "Exames confirmaram a lesão. [1]" in cur["body_tg_html"]
    assert cur["disclaimer_kinds"] == ["unconfirmed"]
    assert cur["disclaimer_text"].startswith("⚠️")
    assert cur["citations"][0]["n"] == 1
    e = (await c.get(f"/api/v1/events/{ev.id}", params={"include": "draft"})).json()
    assert (e["status"], e["draft"]["id"], e["draft"]["state"]) == ("DRAFT", d["id"], "ready")
    again = await c.post(f"/api/v1/events/{ev.id}/drafts", json={}, headers=idem(h))
    assert (again.status_code, again.json()["id"]) == (200, d["id"])

    save = await c.patch(
        f"/api/v1/drafts/{d['id']}",
        json={"body_tg_html": "<p>Meu texto [1]</p><script>x</script>"},
        headers={**h, "If-Match": f'"{d["version"]}"'},
    )
    assert save.status_code == 200, save.text
    s2 = save.json()
    assert (s2["current"]["n"], s2["current"]["origin"], s2["current"]["body_tg_html"]) == (
        2,
        "human",
        "Meu texto [1]",
    )
    assert len(s2["current"]["citations"]) == 1
    assert (
        await c.patch(
            f"/api/v1/drafts/{d['id']}",
            json={"body_tg_html": "x"},
            headers={**h, "If-Match": f'"{d["version"]}"'},
        )
    ).status_code == 412
    forbid = await c.patch(
        f"/api/v1/drafts/{d['id']}",
        json={"body_tg_html": "x", "disclaimer_removed": True},
        headers={**h, "If-Match": f'"{s2["version"]}"'},
    )
    assert (forbid.status_code, forbid.json()["code"]) == (
        403,
        "draft.disclaimer_removal_forbidden",
    )
    long = await c.patch(
        f"/api/v1/drafts/{d['id']}",
        json={"body_tg_html": "a" * 4100},
        headers={**h, "If-Match": f'"{s2["version"]}"'},
    )
    assert long.status_code == 422
    assert "> 4096" in long.json()["errors"][0]["message"]
    regen = await c.post(f"/api/v1/drafts/{d['id']}:regenerate", json={}, headers=h)
    assert (regen.json()["current"]["n"], regen.json()["current"]["origin"]) == (3, "template")
    v1 = (await c.get(f"/api/v1/drafts/{d['id']}/versions/1")).json()
    assert v1["origin"] == "template"
    assert [x["n"] for x in regen.json()["versions"]] == [3, 2, 1]


async def test_ready_event_back_to_draft_on_save_and_editor_removes_disclaimer(
    make_app, client_for, db: Database
) -> None:  # type: ignore[no-untyped-def]
    c, h, ev = await setup(make_app, client_for, db, "editor")
    d = (await c.post(f"/api/v1/events/{ev.id}/drafts", json={}, headers=idem(h))).json()
    e = (await c.get(f"/api/v1/events/{ev.id}")).json()
    r = await c.post(
        f"/api/v1/events/{ev.id}/transitions",
        json={"to": "READY"},
        headers={**h, "If-Match": f'"{e["version"]}"'},
    )
    assert r.json()["status"] == "READY"
    s = await c.patch(
        f"/api/v1/drafts/{d['id']}",
        json={"body_tg_html": "Novo", "disclaimer_removed": True},
        headers={**h, "If-Match": f'"{d["version"]}"'},
    )
    assert s.status_code == 200, s.text
    assert s.json()["current"]["disclaimer_text"] is None
    assert (await c.get(f"/api/v1/events/{ev.id}")).json()["status"] == "DRAFT"


async def test_modes_and_status_rules(make_app, client_for, db: Database) -> None:  # type: ignore[no-untyped-def]
    c, h, ev = await setup(make_app, client_for, db, status=EventStatus.NEW)
    r = await c.post(f"/api/v1/events/{ev.id}/drafts", json={}, headers=idem(h))
    assert (r.status_code, r.json()["code"]) == (409, "draft.event_status_invalid")
    c2, h2, ev2 = await setup(make_app, client_for, db)
    r = await c2.post(f"/api/v1/events/{ev2.id}/drafts", json={"mode": "llm"}, headers=idem(h2))
    assert (r.status_code, r.json()["errors"][0]["field"]) == (422, "mode")
    r = await c2.post(f"/api/v1/events/{ev2.id}/drafts", json={"mode": "empty"}, headers=idem(h2))
    assert (r.status_code, r.json()["current"]["origin"], r.json()["current"]["body_tg_html"]) == (
        201,
        "human",
        "",
    )


async def test_no_sources_fails(make_app, client_for, db: Database) -> None:  # type: ignore[no-untyped-def]
    c, h, ev = await setup(make_app, client_for, db, articles=False)
    r = await c.post(f"/api/v1/events/{ev.id}/drafts", json={}, headers=idem(h))
    assert (r.status_code, r.json()["state"], r.json()["failure_code"]) == (
        201,
        "failed",
        "generation_failed",
    )


async def test_copied_records_audit(make_app, client_for, db: Database) -> None:  # type: ignore[no-untyped-def]
    from sqlalchemy import text

    c, h, ev = await setup(make_app, client_for, db)
    d = (await c.post(f"/api/v1/events/{ev.id}/drafts", json={}, headers=idem(h))).json()
    assert (
        await c.post(f"/api/v1/drafts/{d['id']}:copied", json={"version_n": 1}, headers=h)
    ).status_code == 204
    assert (
        await c.post(f"/api/v1/drafts/{d['id']}:copied", json={"version_n": 9}, headers=h)
    ).status_code == 404
    async with db.uow() as u:
        n = (
            await u.session.execute(
                text(
                    "SELECT count(*) FROM audit.audit_log WHERE action='draft.copied' AND target_id=:i"
                ),
                {"i": d["id"]},
            )
        ).scalar()
    assert n == 1


async def test_post_in_another_language_from_brief(make_app, client_for, db: Database) -> None:  # type: ignore[no-untyped-def]
    """Шаблон на pt-BR → версия на ru из AI-брифа → правка остаётся на ru."""
    from sportintel.modules.editorial.infrastructure.briefs_repository import SqlBriefRepository

    c, h, ev = await setup(make_app, client_for, db)
    r = await c.post(f"/api/v1/events/{ev.id}/drafts", json={}, headers=idem(h))
    d = r.json()
    missing = await c.post(
        f"/api/v1/drafts/{d['id']}:regenerate", json={"mode": "brief", "lang": "ru"}, headers=h
    )
    assert missing.status_code == 422
    assert missing.json()["errors"][0]["code"] == "brief_missing"
    async with db.uow() as u:
        await SqlBriefRepository(u.session).upsert(
            {
                "event_id": ev.id,
                "lang": "ru",
                "brief": {
                    "headline": "Педро выбыл",
                    "status": "reported",
                    "summary": ["Обследование подтвердило травму."],
                    "affected": ["Педро"],
                    "impact": "Команда теряет основного нападающего.",
                    "actions": ["Следить за составом"],
                    "source_refs": [1],
                },
                "sources": [{"n": 1, "name": "ge", "tier": "A", "url": "https://ge.globo.com/x"}],
                "article_hash": "x",
                "provider": "fake",
                "model": "fake",
                "prompt_version": "brief/v2",
                "duration_ms": 1,
            },
            datetime(2026, 10, 9, 12, tzinfo=UTC),
        )
    r = await c.post(
        f"/api/v1/drafts/{d['id']}:regenerate", json={"mode": "brief", "lang": "ru"}, headers=h
    )
    assert r.status_code == 200, r.text
    cur = r.json()["current"]
    assert (cur["n"], cur["lang"], cur["origin"]) == (2, "ru", "ai")
    assert cur["body_tg_html"].startswith("<b>⚽ Педро выбыл</b>")
    assert cur["disclaimer_text"].startswith("⚠️ Информация")
    saved = await c.patch(
        f"/api/v1/drafts/{d['id']}",
        json={"body_tg_html": "<b>Педро выбыл</b> — правка"},
        headers={**h, "If-Match": r.headers["ETag"]},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["current"]["lang"] == "ru"
    assert [v["lang"] for v in saved.json()["versions"]] == ["ru", "ru", "en"]
