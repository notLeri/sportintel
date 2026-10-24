import pytest
from tests.api.conftest import dev_login

from sportintel.platform import settings_store

pytestmark = pytest.mark.integration


async def test_check_explains_the_score_and_tries_unsaved_rules(make_app, client_for) -> None:  # type: ignore[no-untyped-def]
    """Экран «Важность»: из чего сложился балл — и как изменится от правок до сохранения."""
    settings_store.clear_cache()
    c = client_for(make_app())
    me = await dev_login(c, "rel@corp.com", "admin")
    h = {"X-CSRF-Token": me["csrf_token"]}
    body = {"title": "Flamengo demite técnico após derrota", "lead": "Jogador com lesão."}

    r = (await c.post("/api/v1/relevance:check", json=body, headers=h)).json()
    assert r["is_sports"]
    parts = {p["name"]: (p["points"], p["where"]) for p in r["parts"]}
    assert parts["Смена тренера"] == (6, "title")  # вес 3 × 2 — слово в заголовке
    assert parts["Травма"] == (2, "body")  # вес 3 × 0,5 — только в тексте (округление)
    assert r["score"] == sum(p["points"] for p in r["parts"])
    assert r["level"] == "HIGH"

    # тот же заголовок при пороге «Высокой» 20 — уже средняя важность; правила не сохранены
    stricter = {**body, "rules": {"level_thresholds": {"HIGH": 20, "MEDIUM": 3, "LOW": 1}}}
    r2 = (await c.post("/api/v1/relevance:check", json=stricter, headers=h)).json()
    assert (r2["score"], r2["level"]) == (r["score"], "MEDIUM")
    assert (await c.post("/api/v1/relevance:check", json=body, headers=h)).json()["level"] == "HIGH"

    bad = {**body, "rules": {"body_weight": 9}}
    assert (await c.post("/api/v1/relevance:check", json=bad, headers=h)).status_code == 422
    off_topic = {"title": "Prêmio Nobel de Literatura anunciado"}
    r3 = (await c.post("/api/v1/relevance:check", json=off_topic, headers=h)).json()
    assert (r3["is_sports"], r3["level"], r3["parts"]) == (False, "IRRELEVANT", [])
