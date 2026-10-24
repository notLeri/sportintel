import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import delete, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from sportintel.modules.editorial.infrastructure.tables import channel_pins as pins
from sportintel.modules.editorial.infrastructure.tables import channels as ch
from sportintel.modules.editorial.infrastructure.tables import publications as pub
from sportintel.platform.errors import ConcurrencyConflict


class SqlChannelRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def all(self, *, active_only: bool = False) -> list[dict[str, Any]]:
        q = select(ch).order_by(ch.c.name)
        if active_only:
            q = q.where(ch.c.active.is_(True))
        return [dict(r._mapping) for r in await self.session.execute(q)]

    async def get(self, channel_id: uuid.UUID) -> dict[str, Any] | None:
        row = (await self.session.execute(select(ch).where(ch.c.id == channel_id))).first()
        return dict(row._mapping) if row else None

    async def create(self, values: dict[str, Any], now: datetime) -> None:
        await self.session.execute(insert(ch).values(**values, created_at=now, updated_at=now))

    async def update(
        self, channel_id: uuid.UUID, now: datetime, expected_version: int | None, **values: Any
    ) -> int:
        q = update(ch).where(ch.c.id == channel_id)
        if expected_version is not None:
            q = q.where(ch.c.version == expected_version)
        got = (
            await self.session.execute(
                q.values(**values, updated_at=now, version=ch.c.version + 1).returning(ch.c.version)
            )
        ).scalar()
        if got is None:
            raise ConcurrencyConflict(current=None)
        return int(got)

    async def mark_run(self, channel_id: uuid.UUID, now: datetime) -> None:
        await self.session.execute(update(ch).where(ch.c.id == channel_id).values(last_run_at=now))

    async def published(self, channel_id: uuid.UUID, ids: list[uuid.UUID]) -> set[uuid.UUID]:
        if not ids:
            return set()
        q = select(pub.c.event_id).where(pub.c.channel_id == channel_id, pub.c.event_id.in_(ids))
        return {r[0] for r in await self.session.execute(q)}

    async def record(self, row: dict[str, Any], now: datetime) -> bool:
        """False — событие уже было в канале (гонка двух запусков): второй раз не пишем."""
        res = await self.session.execute(
            pg_insert(pub)
            .values(**row, created_at=now)
            .on_conflict_do_nothing(constraint="uq_publications_channel_event")
            .returning(pub.c.id)
        )
        return res.scalar() is not None

    async def publications(self, channel_id: uuid.UUID, limit: int = 50) -> list[dict[str, Any]]:
        q = (
            select(pub)
            .where(pub.c.channel_id == channel_id)
            .order_by(pub.c.created_at.desc())
            .limit(limit)
        )
        return [dict(r._mapping) for r in await self.session.execute(q)]

    async def pins(self, channel_id: uuid.UUID) -> dict[uuid.UUID, datetime]:
        q = select(pins.c.event_id, pins.c.publish_at).where(pins.c.channel_id == channel_id)
        return {r[0]: r[1] for r in await self.session.execute(q)}

    async def pinned_by(self, channel_id: uuid.UUID) -> dict[uuid.UUID, uuid.UUID]:
        q = select(pins.c.event_id, pins.c.created_by).where(
            pins.c.channel_id == channel_id, pins.c.created_by.is_not(None)
        )
        return {r[0]: r[1] for r in await self.session.execute(q)}

    async def pin(
        self, channel_id: uuid.UUID, event_id: uuid.UUID, at: datetime, by: uuid.UUID | None
    ) -> None:
        stmt = pg_insert(pins).values(
            channel_id=channel_id, event_id=event_id, publish_at=at, created_by=by
        )
        await self.session.execute(
            stmt.on_conflict_do_update(
                index_elements=["channel_id", "event_id"],
                set_={"publish_at": at, "created_by": by},
            )
        )

    async def unpin(self, channel_id: uuid.UUID, event_id: uuid.UUID) -> None:
        await self.session.execute(
            delete(pins).where(pins.c.channel_id == channel_id, pins.c.event_id == event_id)
        )
