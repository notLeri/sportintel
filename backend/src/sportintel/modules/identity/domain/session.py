import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timedelta


@dataclass(frozen=True)
class SessionRecord:
    id_hash: bytes
    user_id: uuid.UUID
    csrf_token: str
    created_at: datetime
    last_seen_at: datetime
    idle_expires_at: datetime
    absolute_expires_at: datetime


@dataclass(frozen=True)
class SessionPolicy:
    idle: timedelta = timedelta(hours=12)
    absolute: timedelta = timedelta(days=7)
    touch_every: timedelta = timedelta(minutes=5)

    def expiries(self, now: datetime) -> tuple[datetime, datetime]:
        """(idle_expires_at, absolute_expires_at) новой сессии."""
        absolute = now + self.absolute
        return min(now + self.idle, absolute), absolute

    def is_valid(self, session: SessionRecord, now: datetime) -> bool:
        return now < session.idle_expires_at and now < session.absolute_expires_at

    def should_touch(self, session: SessionRecord, now: datetime) -> bool:
        return now - session.last_seen_at >= self.touch_every

    def touched(self, session: SessionRecord, now: datetime) -> SessionRecord:
        # idle продлевается, но никогда не выходит за absolute
        idle = min(now + self.idle, session.absolute_expires_at)
        return replace(session, last_seen_at=now, idle_expires_at=idle)
