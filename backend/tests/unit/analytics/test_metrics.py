import uuid
from datetime import UTC, datetime, timedelta

from sportintel.modules.analytics.domain.metrics import (
    active_hours,
    draft_edit_ratio,
    median,
    useful_events,
)

T0 = datetime(2026, 10, 9, 12, tzinfo=UTC)
m = lambda n: T0 + timedelta(minutes=n)  # noqa: E731


def test_active_hours_sessions_and_single_actions() -> None:
    assert active_hours([]) == 0
    assert active_hours([m(0)]) == 5 / 60
    assert active_hours([m(0), m(10), m(20)]) == 25 / 60
    assert active_hours([m(0), m(16)]) == 10 / 60  # пауза > 15 мин рвёт сессию


def test_useful_events_first_transition_and_exclusions() -> None:
    a, b, c = (uuid.UUID(int=i) for i in (1, 2, 3))
    u1, u2 = uuid.uuid4(), uuid.uuid4()
    trans = [
        {"event_id": a, "actor_id": u1, "at": m(5), "to_status": "SELECTED"},
        {"event_id": a, "actor_id": u2, "at": m(9), "to_status": "READY"},
        {"event_id": b, "actor_id": u2, "at": m(1), "to_status": "SELECTED"},
        {"event_id": c, "actor_id": u1, "at": m(2), "to_status": "REVIEWING"},
    ]
    cur = {
        a: {"status": "READY", "rejection_reason": None},
        b: {"status": "REJECTED", "rejection_reason": "DUPLICATE"},
        c: {"status": "REVIEWING", "rejection_reason": None},
    }
    assert useful_events(trans, cur) == {a: (u1, m(5))}


def test_edit_ratio_and_median() -> None:
    assert draft_edit_ratio("<b>abc</b>", "abc") == 0
    assert draft_edit_ratio("abcd", "wxyz") == 1
    assert (median([3, 1, 2]), median([1, 2, 3, 4]), median([])) == (2, 2.5, None)
