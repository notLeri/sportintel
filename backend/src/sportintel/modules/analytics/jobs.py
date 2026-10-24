"""Фоновые задачи модуля analytics (CONV §10)."""

from datetime import timedelta

from sportintel.modules.analytics.infrastructure import queries
from sportintel.platform import ai_usage, jobs

RETENTION = timedelta(days=90)


@jobs.periodic("analytics.purge_heartbeats", cron="40 4 * * *")
async def purge_heartbeats(timestamp: int) -> None:
    rt = jobs.runtime()
    async with rt.db.uow() as uow:
        await queries.purge_heartbeats(uow.session, rt.clock.now() - RETENTION)
        await ai_usage.purge(uow.session, rt.clock.now() - RETENTION)
