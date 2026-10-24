import pytest

from sportintel.modules.sources.domain.health import MAX_DELAY_S, compute_health, next_poll_delay
from sportintel.modules.sources.domain.values import SourceHealth


@pytest.mark.parametrize(
    ("failures", "expected"),
    [
        (0, 300),
        (1, 600),
        (2, 1200),
        (3, 2400),
        (4, 4800),
        (5, 9600),
        (6, 19200),
        (7, MAX_DELAY_S),
        (10, MAX_DELAY_S),
        (1000, MAX_DELAY_S),
    ],
)
def test_next_poll_delay(failures: int, expected: int) -> None:
    assert next_poll_delay(300, failures) == expected


@pytest.mark.parametrize(
    ("recent", "failures", "health"),
    [
        ([], 0, SourceHealth.UNKNOWN),
        (["ok"], 0, SourceHealth.OK),
        (["not_modified", "ok"], 0, SourceHealth.OK),
        (["error", "ok"], 1, SourceHealth.DEGRADED),
        (["error"] * 4, 4, SourceHealth.DEGRADED),
        (["error"] * 5, 5, SourceHealth.DOWN),
        (["ok", "error", "error", "error", "error", "error"], 0, SourceHealth.OK),  # восстановился
    ],
)
def test_compute_health(recent: list[str], failures: int, health: SourceHealth) -> None:
    assert compute_health(recent, failures) == health
