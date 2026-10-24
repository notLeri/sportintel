"""Задачи модуля sources (CONV §10)."""

import structlog

from sportintel.modules.sources.infrastructure.repository import SqlSourceRepository
from sportintel.platform import jobs

DUE_BATCH = 50
_log = structlog.get_logger("sportintel.sources")


async def schedule_due_now() -> int:
    rt = jobs.runtime()
    async with rt.db.uow() as uow:
        due = await SqlSourceRepository(uow.session).claim_due(rt.clock.now(), DUE_BATCH)
        for source_id in due:
            # Задача ingestion по имени: sources не импортирует ingestion (CONV §7.2).
            uow.enqueue_after_commit(
                "ingestion.fetch_source",
                queueing_lock=f"fetch_source:{source_id}",
                source_id=str(source_id),
            )
    if due:
        _log.info("sources.due_scheduled", count=len(due))
    return len(due)


@jobs.periodic("sources.schedule_due", cron="* * * * *", queue="scheduler", lock="schedule_due")
async def schedule_due(timestamp: int) -> None:
    await schedule_due_now()
