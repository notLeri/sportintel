import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from sportintel.modules.editorial.infrastructure.tables import event_briefs as b


class SqlBriefRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, event_id: uuid.UUID, lang: str) -> dict[str, Any] | None:
        row = (
            await self.session.execute(select(b).where(b.c.event_id == event_id, b.c.lang == lang))
        ).first()
        return dict(row._mapping) if row else None

    async def hashes(self, keys: list[tuple[uuid.UUID, str]]) -> dict[tuple[uuid.UUID, str], str]:
        if not keys:
            return {}
        q = select(b.c.event_id, b.c.lang, b.c.article_hash).where(
            tuple_(b.c.event_id, b.c.lang).in_(keys)
        )
        return {(r.event_id, r.lang): r.article_hash for r in await self.session.execute(q)}

    async def upsert(self, row: dict[str, Any], now: datetime) -> None:
        values = {**row, "created_at": now}
        await self.session.execute(
            pg_insert(b)
            .values(**values)
            .on_conflict_do_update(index_elements=[b.c.event_id, b.c.lang], set_=values)
        )
