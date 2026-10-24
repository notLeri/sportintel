from datetime import UTC, datetime, timedelta

import pytest
from tests.api.conftest import dev_login
from tests.factories import make_article, make_source

from sportintel.platform.db import Database

pytestmark = pytest.mark.integration
T0 = datetime(2026, 10, 8, 12, tzinfo=UTC)


async def seed(db: Database):  # type: ignore[no-untyped-def]
    async with db.uow() as u:
        a, b = (
            await make_source(u, domain="qa.example.com"),
            await make_source(u, domain="qb.example.com"),
        )
        rows = [
            await make_article(
                u,
                a,
                title="São Paulo vence o clássico",
                lead="Lesões preocupam",
                published_at=T0 - timedelta(hours=1),
            ),
            await make_article(u, a, title="Flamengo treina", published_at=T0 - timedelta(hours=2)),
            await make_article(
                u, b, title="Grêmio contrata lateral", published_at=T0 - timedelta(days=3)
            ),
        ]
    return a, b, rows


async def client(make_app, client_for):  # type: ignore[no-untyped-def]
    c = client_for(make_app())
    await dev_login(c, "reader@corp.com", "researcher")
    return c


async def test_filters_and_detail(make_app, client_for, db: Database) -> None:  # type: ignore[no-untyped-def]
    a, b, rows = await seed(db)
    c = await client(make_app, client_for)
    by_source = (await c.get("/api/v1/articles", params={"source": str(b.id)})).json()["items"]
    assert [i["title"] for i in by_source] == ["Grêmio contrata lateral"]
    assert by_source[0]["source"] == {
        "id": str(b.id),
        "name": b.name,
        "domain": "qb.example.com",
        "tier": "B",
    }
    both = (
        await c.get(
            "/api/v1/articles", params=[("source", f"{a.id},{b.id}"), ("state", "discovered")]
        )
    ).json()["items"]
    assert [i["title"] for i in both][:3] == [
        "São Paulo vence o clássico",
        "Flamengo treina",
        "Grêmio contrata lateral",
    ]
    recent = (
        await c.get(
            "/api/v1/articles",
            params={"from": (T0 - timedelta(days=1)).isoformat(), "source": str(a.id)},
        )
    ).json()["items"]
    assert len(recent) == 2
    detail = (await c.get(f"/api/v1/articles/{rows[0].id}")).json()
    assert (detail["lead"], detail["event_id"], detail["enrichment"]) == (
        "Lesões preocupam",
        None,
        None,
    )
    assert (await c.get("/api/v1/articles/0192f6a1-0000-7000-8000-00000000dead")).status_code == 404
    assert (await c.get("/api/v1/articles", params={"state": "bogus"})).status_code == 422


@pytest.mark.parametrize(
    ("q", "title"),
    [
        ("sao paulo", "São Paulo vence o clássico"),
        ("lesoes", "São Paulo vence o clássico"),
        ("gremio", "Grêmio contrata lateral"),
    ],
)
async def test_search_ignores_accents(
    make_app, client_for, db: Database, q: str, title: str
) -> None:  # type: ignore[no-untyped-def]
    await seed(db)
    c = await client(make_app, client_for)
    items = (await c.get("/api/v1/articles", params={"q": q})).json()["items"]
    assert [i["title"] for i in items] == [title]


async def test_three_pages_without_gaps_when_new_article_arrives(
    make_app, client_for, db: Database
) -> None:  # type: ignore[no-untyped-def]
    async with db.uow() as u:
        s = await make_source(u, domain="pages.example.com")
        for i in range(6):
            await make_article(u, s, title=f"Nota {i}", published_at=T0 - timedelta(minutes=i))
    c = await client(make_app, client_for)
    params = {"source": str(s.id), "limit": 2}
    seen: list[str] = []
    page = (await c.get("/api/v1/articles", params=params)).json()
    seen += [i["title"] for i in page["items"]]
    async with db.uow() as u:  # новая статья наверху списка между запросами
        await make_article(u, s, title="Nova", published_at=T0 + timedelta(minutes=1))
    while page["next_cursor"]:
        page = (
            await c.get("/api/v1/articles", params={**params, "cursor": page["next_cursor"]})
        ).json()
        seen += [i["title"] for i in page["items"]]
    assert seen == [f"Nota {i}" for i in range(6)]
