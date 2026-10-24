import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from sportintel.modules.editorial.infrastructure.tables import telegram_draft_versions as v
from sportintel.modules.editorial.infrastructure.tables import telegram_drafts as d
from sportintel.platform.errors import ConcurrencyConflict


class SqlDraftRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, draft_id: uuid.UUID, *, for_update: bool = False) -> dict[str, Any] | None:
        q = select(d).where(d.c.id == draft_id)
        row = (await self.session.execute(q.with_for_update() if for_update else q)).first()
        return dict(row._mapping) if row else None

    async def by_event(
        self, event_id: uuid.UUID, *, for_update: bool = False
    ) -> dict[str, Any] | None:
        q = select(d).where(d.c.event_id == event_id)
        row = (await self.session.execute(q.with_for_update() if for_update else q)).first()
        return dict(row._mapping) if row else None

    async def events_with_post_in(self, lang: str, since: datetime) -> list[uuid.UUID]:
        """События, чей текущий пост — на языке lang (черновик менялся не раньше since)."""
        q = (
            select(d.c.event_id)
            .join(v, (v.c.draft_id == d.c.id) & (v.c.n == d.c.current_version))
            .where(v.c.lang == lang, d.c.updated_at >= since)
        )
        return list((await self.session.execute(q)).scalars())

    async def needing_ai(self, ids: list[uuid.UUID], lang: str) -> set[uuid.UUID]:
        """Авточерновики, чей текущий пост — шаблон или не на языке lang (правки человека — нет)."""
        if not ids:
            return set()
        q = (
            select(d.c.event_id)
            .join(v, (v.c.draft_id == d.c.id) & (v.c.n == d.c.current_version))
            .where(
                d.c.event_id.in_(ids),
                d.c.created_by.is_(None),
                v.c.origin != "human",
                (v.c.origin == "template") | (v.c.lang != lang),
            )
        )
        return set((await self.session.execute(q)).scalars())

    async def by_events(self, ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, Any]]:
        if not ids:
            return {}
        return {
            r.event_id: dict(r._mapping)
            for r in await self.session.execute(select(d).where(d.c.event_id.in_(ids)))
        }

    async def create(
        self,
        draft_id: uuid.UUID,
        event_id: uuid.UUID,
        state: str,
        created_by: uuid.UUID | None,
        now: datetime,
    ) -> None:
        await self.session.execute(
            pg_insert(d).values(
                id=draft_id,
                event_id=event_id,
                state=state,
                created_by=created_by,
                created_at=now,
                updated_at=now,
            )
        )

    async def update(
        self, draft_id: uuid.UUID, now: datetime, expected_version: int | None = None, **values: Any
    ) -> int:
        q = update(d).where(d.c.id == draft_id)
        if expected_version is not None:
            q = q.where(d.c.version == expected_version)
        res = await self.session.execute(
            q.values(**values, updated_at=now, version=d.c.version + 1).returning(d.c.version)
        )
        got = res.scalar()
        if got is None:
            raise ConcurrencyConflict(current=None)
        return int(got)

    async def add_version(
        self, draft_id: uuid.UUID, n: int, row: dict[str, Any], now: datetime
    ) -> None:
        await self.session.execute(
            pg_insert(v).values(draft_id=draft_id, n=n, created_at=now, **row)
        )

    async def version(self, draft_id: uuid.UUID, n: int) -> dict[str, Any] | None:
        row = (
            await self.session.execute(select(v).where(v.c.draft_id == draft_id, v.c.n == n))
        ).first()
        return dict(row._mapping) if row else None

    async def versions(self, draft_id: uuid.UUID) -> list[dict[str, Any]]:
        q = (
            select(v.c.n, v.c.lang, v.c.origin, v.c.author_id, v.c.created_at)
            .where(v.c.draft_id == draft_id)
            .order_by(v.c.n.desc())
        )
        return [dict(r._mapping) for r in await self.session.execute(q)]
