import uuid
from datetime import UTC, datetime, timedelta

import pytest

from sportintel.composition.health_rules import Firing, HealthInputs, SourceHealth, evaluate, plan
from sportintel.platform.settings_store import HealthWatch

CFG = HealthWatch()
DAY = datetime(2026, 10, 9, 15, tzinfo=UTC)  # 12:00 BRT — активные часы
NIGHT = datetime(2026, 10, 9, 6, tzinfo=UTC)  # 03:00 BRT


def src(**kw) -> SourceHealth:  # type: ignore[no-untyped-def]
    base = dict(
        id=uuid.UUID(int=1),
        name="ge",
        tier="A",
        active=True,
        last_new_article_at=DAY - timedelta(hours=7),
        consecutive_failures=0,
        had_articles_7d=True,
    )
    return SourceHealth(**{**base, **kw})


def keys(i: HealthInputs, now: datetime = DAY) -> set[str]:
    return {f.alert_key for f in evaluate(i, now, CFG)}


def test_queue_and_lag_boundaries() -> None:
    assert keys(HealthInputs({"fetch": 15 * 60, "ai": 15 * 60 + 1}, 15 * 60)) == {
        "queue_stalled:ai"
    }
    assert keys(HealthInputs({"cluster": 99999}, 15 * 60 + 1)) == {"ingest_lag"}


@pytest.mark.parametrize(
    ("s", "now", "fires"),
    [
        (src(), DAY, True),
        (src(), NIGHT, False),
        (src(last_new_article_at=DAY - timedelta(hours=5)), DAY, False),
        (src(tier="B"), DAY, False),
        (src(had_articles_7d=False), DAY, False),  # новый источник — не «молчит»
        (src(active=False), DAY, False),
    ],
)
def test_source_silent(s: SourceHealth, now: datetime, fires: bool) -> None:
    assert (f"source_silent:{s.id}" in keys(HealthInputs({}, None, [s]), now)) is fires


def test_source_failing() -> None:
    assert keys(HealthInputs({}, None, [src(consecutive_failures=5, last_new_article_at=DAY)])) == {
        f"source_failing:{uuid.UUID(int=1)}"
    }


def test_plan_repeat_and_resolve() -> None:
    f = [Firing("ingest_lag", "lag")]
    assert plan(f, {}, DAY, 60) == [("ingest_lag", "🔴 lag", True)]
    recent = {
        "ingest_lag": {
            "firing": True,
            "last_sent_at": DAY - timedelta(minutes=5),
            "details": {"text": "lag"},
        }
    }
    assert plan(f, recent, DAY, 60) == []
    old = {
        "ingest_lag": {
            "firing": True,
            "last_sent_at": DAY - timedelta(minutes=61),
            "details": {"text": "lag"},
        }
    }
    assert plan(f, old, DAY, 60) == [("ingest_lag", "🔴 lag", True)]
    assert plan([], recent, DAY, 60) == [("ingest_lag", "✅ Исправлено: lag", False)]
