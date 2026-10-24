import pytest
from tests.api.conftest import dev_login
from tests.factories import make_article, make_entity, make_event, make_source

from sportintel.modules.events.infrastructure.repository import SqlEventRepository
from sportintel.modules.taxonomy.infrastructure.repository import SqlTaxonomyRepository
from sportintel.platform.db import Database

pytestmark = pytest.mark.integration


async def test_search_fts_alias_source_and_sport(make_app, client_for, db: Database) -> None:  # type: ignore[no-untyped-def]
    async with db.uow() as u:
        espn = await make_source(u, domain="espn-s.example.com", name="ESPN Teste")
        ge = await make_source(u, domain="ge-s.example.com", name="GE Teste")
        gabi = await make_entity(u, "Gabriel Barbosa Teste")
        await SqlTaxonomyRepository(u.session).add_aliases(gabi.id, ["Gabigolzinho"])
        e1 = await make_event(
            u,
            [await make_article(u, ge)],
            title="Atacante treina separado",
            sport_id="football",
            search_doc="Atacante treina separado\nGE Teste",
        )
        await SqlEventRepository(u.session).replace_entities(e1.id, [(gabi.id, "player", 1, False)])
        await make_event(
            u,
            [await make_article(u, espn)],
            title="Lesão de Pedro preocupa",
            sport_id="football",
            search_doc="Lesão de Pedro preocupa\nlesão no joelho\nESPN Teste",
        )
        await make_event(
            u,
            [await make_article(u, ge)],
            title="Lesão no vôlei",
            sport_id="volleyball",
            search_doc="Lesão no vôlei\nlesão",
        )
    c = client_for(make_app())
    await dev_login(c, "search@corp.com", "researcher")

    async def titles(**params: str) -> list[str]:
        r = await c.get("/api/v1/events", params=params)
        assert r.status_code == 200, r.text
        return [i["title"] for i in r.json()["items"]]

    assert await titles(q="Gabigolzinho") == ["Atacante treina separado"]
    assert await titles(q="ESPN Teste") == ["Lesão de Pedro preocupa"]
    assert await titles(q="lesao Pedro") == ["Lesão de Pedro preocupa"]
    assert await titles(q="lesao", sport="volleyball") == ["Lesão no vôlei"]
    page = (await c.get("/api/v1/events", params={"q": "lesao", "limit": 1})).json()
    assert page["next_cursor"]
    nxt = await titles(q="lesao", limit="1", cursor=page["next_cursor"])
    assert nxt
    assert nxt[0] != page["items"][0]["title"]
