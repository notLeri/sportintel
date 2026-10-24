import uuid
from datetime import UTC, datetime, timedelta

from sportintel.modules.events.domain.policies.relevance import ArticleRelevance, compute_relevance
from sportintel.modules.events.domain.values import AssessmentOrigin
from sportintel.modules.events.domain.values import Relevance as R

T0 = datetime(2026, 10, 8, tzinfo=UTC)


def a(level: R, rationale: str = "r", minutes: int = 0, dup: bool = False) -> ArticleRelevance:
    return ArticleRelevance(uuid.uuid4(), level, rationale, T0 + timedelta(minutes=minutes), dup)


def test_max_level_and_earliest_rationale() -> None:
    r = compute_relevance(
        [a(R.LOW, "x"), a(R.HIGH, "late", 5), a(R.HIGH, "early", 1)], None, None, False
    )
    assert (r.level, r.rationale, r.origin) == (R.HIGH, "early", AssessmentOrigin.AI)


def test_duplicates_ignored_and_empty() -> None:
    assert compute_relevance([a(R.HIGH, dup=True)], None, None, False).level == R.LOW


def test_priority_up_unless_rules_already_counted_it() -> None:
    up = compute_relevance([a(R.MEDIUM, "base")], 2, None, False)
    assert (up.level, up.origin) == (R.HIGH, AssessmentOrigin.RULE)
    assert up.rationale == "base · priority_up"  # код; текст — на языке интерфейса
    same = compute_relevance(
        [a(R.MEDIUM)], 2, 2, False, priorities_in_articles=True, base_origin=AssessmentOrigin.RULE
    )
    assert same.level == R.MEDIUM


def test_down_modifiers_floor_at_low() -> None:
    assert compute_relevance([a(R.LOW)], -1, None, True).level == R.LOW
    assert compute_relevance([a(R.HIGH)], None, None, True, "ru").rationale.endswith(" · stale")
    assert compute_relevance([a(R.IRRELEVANT)], 2, 2, False).level == R.IRRELEVANT
