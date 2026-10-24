from datetime import UTC, date, datetime

from sportintel.modules.intelligence.application.seed_rules import SEED_ENRICH_RULES
from sportintel.modules.intelligence.domain.enrich_output import Claim, EnrichOutput, RelevanceOut
from sportintel.modules.intelligence.domain.rules import (
    ArticleInput,
    Found,
    detect_sport,
    is_clickbait,
    postprocess_clean,
)
from sportintel.modules.intelligence.domain.values import ClaimAttribute, ClaimModality, Relevance
from sportintel.platform.settings_store import EnrichRules

RULES = EnrichRules.model_validate(SEED_ENRICH_RULES)


def art(
    url: str = "https://ge.globo.com/x",
    title: str = "t",
    lead: str | None = None,
    cats: tuple[str, ...] = (),
) -> ArticleInput:
    return ArticleInput(url, title, lead, None, cats, "pt-BR", datetime(2026, 10, 8, tzinfo=UTC))


def test_sport_from_url_category_keywords() -> None:
    assert detect_sport(art("https://ge.globo.com/basquete/nbb/x"), RULES, [])[0] == "basketball"
    assert detect_sport(art(cats=("Vôlei",)), RULES, [])[0] == "volleyball"
    assert (
        detect_sport(art(title="Tenista brasileiro avança no ATP de Pequim"), RULES, [])[0]
        == "tennis"
    )
    assert detect_sport(art(title="Notícia sem pistas"), RULES, [])[0] is None


def test_clickbait() -> None:
    assert is_clickbait("Você não vai acreditar no que o técnico disse", RULES)
    assert not is_clickbait("Flamengo vence o Palmeiras", RULES)


def test_postprocess_drops_invented_quotes_and_future_dates() -> None:
    a = art(title="Pedro sente lesão", lead="O atacante sentiu dores na coxa")
    out = EnrichOutput(
        "pt-BR",
        False,
        "football",
        None,
        [],
        [
            Claim(
                "Pedro",
                ClaimAttribute.INJURY,
                "out",
                ClaimModality.CONFIRMED,
                "sentiu dores na coxa",
            ),
            Claim(
                "Pedro", ClaimAttribute.INJURY, "out", ClaimModality.CONFIRMED, "citação inventada"
            ),
        ],
        ["sondagem", "dores"],
        False,
        date(2026, 12, 1),
        "",
        RelevanceOut(Relevance.HIGH, "x"),
    )
    clean = postprocess_clean(out, a, {"football"})
    assert [c.quote for c in clean.claims] == ["sentiu dores na coxa"]
    assert clean.rumor_markers == ["dores"]
    assert clean.event_date_hint is None
    assert clean.relevance.level == Relevance.IRRELEVANT  # is_sports=false
    assert clean.headline_neutral == "Pedro sente lesão"


CNN = "https://www.cnnbrasil.com.br/internacional/x/"


def team(name: str, in_title: bool = True) -> Found:
    return Found(name, "team", "football", 2, name, in_title, name)


def test_ambiguous_name_or_single_keyword_is_not_a_sport() -> None:
    """Ложные срабатывания из прогона 2026-10-09: омонимы и одиночные ключевые слова."""
    nobel = art(CNN, "Anistia Internacional comenta o Nobel da Paz")
    assert detect_sport(nobel, RULES, [team("Internacional")])[0] is None
    eggs = art(CNN, "Produção de ovos cresce em São Paulo")
    assert detect_sport(eggs, RULES, [team("São Paulo")])[0] is None
    mec = art(CNN, "MEC prorroga prazo de finalização do Enem")
    assert detect_sport(mec, RULES, [])[0] is None


def test_unambiguous_club_or_two_signals_still_detect_football() -> None:
    assert detect_sport(art(CNN, "Grêmio sofre transfer ban"), RULES, [team("Grêmio")])[0] == (
        "football"
    )
    derby = art(CNN, "São Paulo e Santos empatam no clássico")
    assert detect_sport(derby, RULES, [team("São Paulo"), team("Santos")])[0] == "football"
    goal = art(CNN, "Internacional marca gol no fim e vence")
    assert detect_sport(goal, RULES, [team("Internacional")])[0] == "football"


def test_rule_words_by_language_and_legacy_keywords() -> None:
    """Слова сигнала — по языкам источников; старый плоский список раскладывается сам."""
    from sportintel.platform.settings_store import EnrichRules, RelevanceRule

    r = RelevanceRule.model_validate(
        {"name": "Травма", "weight": 3, "keywords": ["lesão", "травма"]}
    )
    assert r.words == {"pt-BR": ["lesão"], "ru": ["травма"]}
    rules = EnrichRules.model_validate({"rumor_markers": ["estaria", "по данным"]})
    assert rules.rumor_markers == {"pt-BR": ["estaria"], "ru": ["по данным"]}
    assert set(rules.all_rumor_markers) == {"estaria", "по данным"}
