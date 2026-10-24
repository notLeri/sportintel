from datetime import UTC, date, datetime

import pytest

from sportintel.modules.events.domain.stale import is_stale_by_hint

AT = datetime(2026, 10, 10, 2, tzinfo=UTC)  # в BRT это ещё 9 октября


@pytest.mark.parametrize(
    ("hints", "stale"),
    [
        ([], False),
        ([None, None], False),
        ([date(2026, 10, 9)], False),
        ([date(2026, 10, 6)], False),  # ровно 3 дня до 9-го по BRT — не старая
        ([date(2026, 10, 5)], True),
        ([date(2026, 10, 1), date(2026, 10, 9)], True),  # половина
        ([date(2026, 10, 1), date(2026, 10, 9), date(2026, 10, 9)], False),
        ([date(2026, 10, 1), None, None], True),
    ],
)
def test_hint_table(hints: list[date | None], stale: bool) -> None:
    assert is_stale_by_hint(hints, AT) is stale
