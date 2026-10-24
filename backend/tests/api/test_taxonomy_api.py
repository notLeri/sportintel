import pytest
from tests.api.conftest import dev_login

pytestmark = pytest.mark.integration


async def test_sports_and_entity_autocomplete(make_app, client_for) -> None:  # type: ignore[no-untyped-def]
    c = client_for(make_app())
    await dev_login(c, "tax@corp.com", "researcher")
    r = await c.get("/api/v1/taxonomy/sports")
    assert r.status_code == 200, r.text
    assert r.headers["Cache-Control"] == "private, max-age=300"
    assert r.json()["items"][0] == {
        "id": "football",
        "name": "Футбол",  # имя на языке пользователя (новые — ru)
        "name_i18n": r.json()["items"][0]["name_i18n"],
        "sort": 10,
    }
    flam = (await c.get("/api/v1/taxonomy/entities", params={"q": "Flam"})).json()["items"]
    assert flam[0]["name"] == "Flamengo"
    comps = (
        await c.get("/api/v1/taxonomy/entities", params={"q": "Liberta", "kind": "competition"})
    ).json()["items"]
    assert [x["kind"] for x in comps] == ["competition"] * len(comps)
    assert comps
    assert comps[0]["name"] == "Кубок Либертадорес"  # на языке интерфейса (ru)
    by_ids = (await c.get("/api/v1/taxonomy/entities", params={"ids": flam[0]["id"]})).json()[
        "items"
    ]
    assert [x["name"] for x in by_ids] == ["Flamengo"]
    assert (await c.get("/api/v1/taxonomy/entities", params={"q": "F"})).json()["items"] == []
    assert (
        await c.get("/api/v1/taxonomy/entities", params={"q": "x", "kind": "nope"})
    ).status_code == 422
