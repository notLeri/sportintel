from typing import Any

from sqlalchemy import literal, select, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from sportintel.modules.audit.infrastructure.tables import audit_log


class SqlAuditStore:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def insert(self, row: dict[str, Any]) -> None:
        await self.session.execute(pg_insert(audit_log).values(**row))

    async def list(
        self,
        *,
        context_event_id: Any = None,
        target_type: str | None = None,
        target_id: str | None = None,
        after: tuple[Any, int] | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        q = select(audit_log)
        if context_event_id is not None:
            q = q.where(audit_log.c.context_event_id == context_event_id)
        if target_type is not None:
            q = q.where(audit_log.c.target_type == target_type, audit_log.c.target_id == target_id)
        if after:
            q = q.where(
                tuple_(audit_log.c.at, audit_log.c.id)
                < tuple_(literal(after[0]), literal(after[1]))
            )
        q = q.order_by(audit_log.c.at.desc(), audit_log.c.id.desc()).limit(limit)
        return [dict(r._mapping) for r in await self.session.execute(q)]
