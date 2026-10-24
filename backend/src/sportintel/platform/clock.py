from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class FrozenClock:
    def __init__(self, at: datetime) -> None:
        if at.tzinfo is None:
            raise ValueError("FrozenClock requires a tz-aware datetime")
        self._at = at.astimezone(UTC)

    def now(self) -> datetime:
        return self._at

    def advance(self, seconds: float) -> None:
        self._at += timedelta(seconds=seconds)
