import uuid
from datetime import UTC, datetime, timedelta

from sportintel.modules.events.domain.evidence import ArticleEvidence, select_fragments

T0 = datetime(2026, 10, 8, tzinfo=UTC)


def art(
    tier: str | None, minutes: int, text: str | None = None, quotes: tuple[str, ...] = ()
) -> ArticleEvidence:
    return ArticleEvidence(
        uuid.uuid4(),
        f"src-{tier}",
        tier,
        T0 + timedelta(minutes=minutes),
        f"T{tier}",
        "Lead.",
        text,
        quotes,
    )


def test_tier_order_round_robin_and_numbering() -> None:
    a, b = art("B", 0, "Lead.\nP1\nP2\nP3"), art("OFFICIAL", 5, "Q1\nQ2")
    frags = select_fragments([a, b], 3)
    assert [f.n for f in frags] == [1, 2, 3]
    assert [f.article_id for f in frags] == [b.article_id, a.article_id, b.article_id]
    assert frags[0].text == "TOFFICIAL. Lead."


def test_claim_quotes_pick_paragraphs_and_clip() -> None:
    a = art(
        "A",
        0,
        "irrelevante aqui\nPedro sofreu lesão grave\n" + "x" * 900,
        quotes=("Pedro sofreu lesão",),
    )
    frags = select_fragments([a], 12)
    assert frags[1].text == "Pedro sofreu lesão grave"
    assert len(select_fragments([art("A", 0, "y" * 900)], 12)[1].text) == 600
