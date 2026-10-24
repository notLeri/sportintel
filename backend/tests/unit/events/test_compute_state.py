import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace as NS

from sportintel.modules.events.domain.computed import RefreshInputs, compute_state, trim_sentences
from sportintel.modules.events.domain.values import (
    ArticleLink,
    AttachMethod,
    Reliability,
    TextOrigin,
)

T0 = datetime(2026, 10, 8, tzinfo=UTC)
TEAM, PLAYER = uuid.uuid4(), uuid.uuid4()
SRC = {
    k: NS(id=uuid.uuid4(), name=f"Fonte {k}", tier=t, owner_group=g)
    for k, t, g in [
        ("ge", "A", "globo"),
        ("g1", "A", "globo"),
        ("cnn", "B", None),
        ("cbf", "OFFICIAL", "cbf"),
    ]
}
ENTS = {
    TEAM: NS(kind="team", priority=2, name="Flamengo"),
    PLAYER: NS(kind="player", priority=0, name="Pedro"),
}


def art(
    src: str,
    minutes: int,
    sport: str | None,
    ents: list[uuid.UUID],
    title: str = "t",
    lead: str | None = None,
) -> tuple:
    a = NS(
        id=uuid.uuid4(),
        source_id=SRC[src].id,
        title=title,
        lead=lead,
        published_at=T0 + timedelta(minutes=minutes),
        discovered_at=T0 + timedelta(minutes=minutes + 1),
    )
    e = NS(
        sport_id=sport,
        competition_id=None,
        entities=[{"entity_id": x} for x in ents],
        relevance="MEDIUM",
        relevance_rationale="r",
        rumor_markers=[],
        clickbait=False,
        embedding=None,
        method="rules",
    )
    return a, e


def inputs(rows: list[tuple], dup: set[int] = frozenset()) -> RefreshInputs:  # type: ignore[assignment]
    links = [
        ArticleLink(a.id, T0, None, AttachMethod.AUTO, False, n in dup)
        for n, (a, _) in enumerate(rows)
    ]
    return RefreshInputs(
        links,
        {a.id: a for a, _ in rows},
        {a.id: e for a, e in rows},
        {s.id: s for s in SRC.values()},
        ENTS,
    )


def test_majority_sport_with_tie_takes_earliest() -> None:
    s = compute_state(
        inputs(
            [
                art("cnn", 5, "volleyball", []),
                art("ge", 1, "football", []),
                art("g1", 9, "volleyball", []),
                art("cbf", 0, "football", []),
            ]
        )
    )
    assert s.sport_id == "football"  # 2:2, самая ранняя — football


def test_duplicates_do_not_count_for_independence() -> None:
    s = compute_state(
        inputs(
            [
                art("ge", 0, "football", [TEAM, PLAYER]),
                art("g1", 1, "football", [TEAM]),
                art("cnn", 2, "football", [TEAM]),
            ],
            dup={2},
        )
    )
    assert (s.article_count, s.source_count, s.independent_source_count, len(s.source_ids)) == (
        3,
        2,
        1,
        3,
    )
    assert s.reliability
    assert s.reliability.level == Reliability.MEDIUM  # одна группа globo
    assert s.entities[0] == (TEAM, "team")
    assert s.entity_mentions[TEAM] == 2


def test_extractive_title_prefers_official_and_search_doc() -> None:
    rows = [
        art("ge", 0, "football", [TEAM], title="GE primeiro", lead="Lead GE."),
        art(
            "cbf",
            5,
            "football",
            [TEAM],
            title="CBF oficial",
            lead="Primeira frase. Segunda frase longa demais.",
        ),
    ]
    i = inputs(rows)
    i.lead_max_chars = 20
    s = compute_state(i)
    assert (s.title, s.title_origin, s.summary) == (
        "CBF oficial",
        TextOrigin.SOURCE,
        "Primeira frase.",
    )
    assert "Flamengo" in s.search_doc
    assert "Fonte cbf" in s.search_doc
    assert s.occurred_at == T0


def test_no_articles_and_centroid() -> None:
    s = compute_state(inputs([]))
    assert (s.reliability.level if s.reliability else None, s.article_count, s.title) == (
        Reliability.UNKNOWN,
        0,
        None,
    )
    a, e = art("ge", 0, "football", [])
    e.embedding = [3.0, 4.0]
    assert compute_state(inputs([(a, e)])).centroid == [0.6, 0.8]


def test_trim_sentences() -> None:
    assert trim_sentences("Uma. Duas.", 100) == "Uma. Duas."
    assert trim_sentences("x" * 30, 10).endswith("…")
