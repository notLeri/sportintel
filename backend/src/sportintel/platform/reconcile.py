"""Сверка: находит сущности, застрявшие из-за потерянной постановки, и ставит задачи заново."""

import structlog

from sportintel.platform import jobs

_log = structlog.get_logger("sportintel.reconcile")


async def run_reconcile() -> dict[str, int]:
    rt = jobs.runtime()
    counts: dict[str, int] = {}
    for name, rule in jobs.RECONCILE_RULES.items():
        try:
            async with rt.db.uow() as uow:
                counts[name] = await rule(uow, rt.clock)
        except Exception:
            _log.exception("platform.reconcile_rule_failed", rule=name)
            continue
        _log.info("platform.reconcile_rule_completed", rule=name, count=counts[name])

    # Задачи прерванного worker (нет heartbeat) возвращаются в очередь (BE-T0.5 §12).
    stalled = list(await jobs.JOBS.job_manager.get_stalled_jobs())
    for job in stalled:
        await jobs.JOBS.job_manager.retry_job(job)
    counts["stalled_jobs"] = len(stalled)
    if stalled:
        _log.warning("platform.stalled_jobs_retried", count=len(stalled))
    return counts


@jobs.periodic("platform.reconcile", cron="*/5 * * * *", lock="reconcile")
async def reconcile(timestamp: int) -> None:
    await run_reconcile()


@jobs.periodic("platform.heartbeat", cron="*/5 * * * *")
async def heartbeat(timestamp: int) -> None:
    _log.info("platform.heartbeat", scheduled_at=timestamp)


@jobs.periodic("platform.purge_idempotency", cron="17 * * * *")
async def purge_idempotency(timestamp: int) -> None:
    from sportintel.platform.idempotency import purge_expired

    rt = jobs.runtime()
    _log.info("platform.idempotency_purged", count=await purge_expired(rt.db, rt.clock.now()))


DONE_JOBS_KEEP_H = 7 * 24  # успешные задачи: недели хватает разбора «что было вчера»
FAILED_JOBS_KEEP_H = 30 * 24  # упавшие — дольше: их повторяют из «Админка → Конвейер»


@jobs.periodic("platform.purge_old_jobs", cron="43 3 * * *", lock="purge_old_jobs")
async def purge_old_jobs(timestamp: int) -> None:
    """Без очистки procrastinate_jobs/_events растут быстрее самих данных и съедают диск."""
    manager = jobs.JOBS.job_manager
    await manager.delete_old_jobs(nb_hours=DONE_JOBS_KEEP_H)
    await manager.delete_old_jobs(
        nb_hours=FAILED_JOBS_KEEP_H,
        include_failed=True,
        include_cancelled=True,
        include_aborted=True,
    )
    _log.info("platform.old_jobs_purged", done_h=DONE_JOBS_KEEP_H, failed_h=FAILED_JOBS_KEEP_H)
