"""Здоровье источника и backoff опроса (BE-T1.9)."""

from collections.abc import Sequence

from sportintel.modules.sources.domain.values import SourceHealth

MAX_DELAY_S = 6 * 3600
DOWN_AFTER_FAILURES = 5


def next_poll_delay(poll_interval_s: int, consecutive_failures: int) -> int:
    """Экспоненциальный backoff: interval · 2^failures, не больше 6 часов."""
    if consecutive_failures <= 0:
        return poll_interval_s
    # min до возведения в степень: без огромных чисел при длинной серии сбоев
    return int(min(poll_interval_s * (1 << min(consecutive_failures, 32)), MAX_DELAY_S))


def compute_health(recent: Sequence[str], consecutive_failures: int) -> SourceHealth:
    """recent — статусы последних запусков (новые первыми)."""
    if not recent:
        return SourceHealth.UNKNOWN
    if consecutive_failures >= DOWN_AFTER_FAILURES:
        return SourceHealth.DOWN
    if consecutive_failures >= 1:
        return SourceHealth.DEGRADED
    return SourceHealth.OK
