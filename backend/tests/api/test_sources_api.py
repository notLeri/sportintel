import pytest
from tests.api.conftest import dev_login

pytestmark = pytest.mark.integration

NEW = {
    "name": "Lance!",
    "base_url": "https://www.lance.com.br",
    "kind": "rss",
    "feed_urls": ["https://www.lance.com.br/feed.xml"],
    "tier": "B",
    "owner_group": "lance",
}


async def admin(make_app, client_for):  # type: ignore[no-untyped-def]
    c = client_for(make_app())
    me = await dev_login(c, "admin@corp.com", "admin")
    return c, {"X-CSRF-Token": me["csrf_token"]}


async def test_researcher_reads_brief_but_cannot_write(make_app, client_for) -> None:  # type: ignore[no-untyped-def]
    c = client_for(make_app())
    me = await dev_login(c, "r@corp.com", "researcher")
    h = {"X-CSRF-Token": me["csrf_token"]}
    r = await c.get("/api/v1/sources")
    assert r.status_code == 200
    assert {"id", "name", "domain", "tier", "region", "active"} == set(r.json()["items"][0])
    assert (await c.get("/api/v1/sources?view=admin")).status_code == 403
    assert (await c.post("/api/v1/sources", json=NEW, headers=h)).status_code == 403


async def test_admin_create_detail_and_duplicate(make_app, client_for) -> None:  # type: ignore[no-untyped-def]
    c, h = await admin(make_app, client_for)
    r = await c.post("/api/v1/sources", json=NEW, headers=h)
    assert r.status_code == 201, r.text
    body = r.json()
    assert (body["domain"], body["version"], r.headers["etag"]) == ("lance.com.br", 1, '"1"')
    assert "feed_cache" not in body
    got = await c.get(f"/api/v1/sources/{body['id']}")
    assert (got.json()["name"], got.headers["etag"]) == ("Lance!", '"1"')
    dup = await c.post("/api/v1/sources", json=NEW, headers=h)
    assert (dup.status_code, dup.json()["code"]) == (409, "source.domain_exists")
    # тот же домен с другим base_url — отдельный источник (каналы на t.me)
    other = await c.post(
        "/api/v1/sources", json={**NEW, "base_url": "https://lance.com.br/x"}, headers=h
    )
    assert other.status_code == 201, other.text
    admin_items = (await c.get("/api/v1/sources?view=admin")).json()["items"]
    lance = next(i for i in admin_items if i["domain"] == "lance.com.br")
    assert (lance["health"], lance["articles_24h"], lance["version"]) == (
        "unknown",
        0,
        1,
    )  # BE-T4.8: счётчик за 24 ч


async def test_create_validation_errors(make_app, client_for) -> None:  # type: ignore[no-untyped-def]
    c, h = await admin(make_app, client_for)
    r = await c.post(
        "/api/v1/sources", json={**NEW, "feed_urls": [], "poll_interval_seconds": 5}, headers=h
    )
    assert r.status_code == 422
    assert {e["field"] for e in r.json()["errors"]} == {"feed_urls", "poll_interval_seconds"}


async def test_patch_concurrency_and_rules(make_app, client_for) -> None:  # type: ignore[no-untyped-def]
    c, h = await admin(make_app, client_for)
    created = (await c.post("/api/v1/sources", json=NEW, headers=h)).json()
    url = f"/api/v1/sources/{created['id']}"
    assert (await c.patch(url, json={"name": "x"}, headers=h)).status_code == 428
    ok = await c.patch(url, json={"name": "Lance", "tier": None}, headers={**h, "If-Match": '"1"'})
    assert ok.status_code == 200, ok.text
    assert (ok.json()["name"], ok.json()["tier"], ok.json()["owner_group"], ok.headers["etag"]) == (
        "Lance",
        None,
        "lance",
        '"2"',
    )
    stale = await c.patch(url, json={"name": "Old"}, headers={**h, "If-Match": '"1"'})
    assert stale.status_code == 412
    assert stale.json()["current"]["name"] == "Lance"
    kind = await c.patch(url, json={"kind": "html"}, headers={**h, "If-Match": '"2"'})
    assert (kind.status_code, kind.json()["errors"][0]) == (
        422,
        {"field": "kind", "code": "immutable", "message": "kind cannot be changed"},
    )
    dom = await c.patch(
        url, json={"base_url": "https://other.com"}, headers={**h, "If-Match": '"2"'}
    )
    assert dom.json()["errors"][0]["code"] == "domain_change_forbidden"
    nul = await c.patch(url, json={"name": None}, headers={**h, "If-Match": '"2"'})
    assert nul.status_code == 422
    assert (
        await c.patch(
            url.replace(created["id"], "0192f6a1-0000-7000-8000-00000000dead"),
            json={"name": "x"},
            headers={**h, "If-Match": '"1"'},
        )
    ).status_code == 404


async def test_reactivation_resets_schedule(make_app, client_for) -> None:  # type: ignore[no-untyped-def]
    c, h = await admin(make_app, client_for)
    created = (await c.post("/api/v1/sources", json={**NEW, "active": False}, headers=h)).json()
    url = f"/api/v1/sources/{created['id']}"
    r = await c.patch(
        url, json={"active": True, "poll_interval_seconds": 120}, headers={**h, "If-Match": '"1"'}
    )
    assert r.status_code == 200
    assert (
        r.json()["active"],
        r.json()["consecutive_failures"],
        r.json()["poll_interval_seconds"],
    ) == (True, 0, 120)


async def test_parser_profile_validated_against_ingestion_registry(make_app, client_for) -> None:  # type: ignore[no-untyped-def]
    c, h = await admin(make_app, client_for)
    bad = await c.post("/api/v1/sources", json={**NEW, "parser_profile": "bogus"}, headers=h)
    assert bad.status_code == 422
    assert bad.json()["errors"][0] == {
        "field": "parser_profile",
        "code": "unknown_profile",
        "message": "known profiles: cbf, default, holidays_brasilapi, holidays_govuk, holidays_openholidays, holidays_ruwiki, telegram",
    }
    good = await c.post(
        "/api/v1/sources",
        json={
            **NEW,
            "base_url": "https://www.cbf.com.br",
            "kind": "html",
            "feed_urls": ["https://www.cbf.com.br/futebol-brasileiro/noticias"],
            "parser_profile": "cbf",
        },
        headers=h,
    )
    assert good.status_code == 201, good.text
