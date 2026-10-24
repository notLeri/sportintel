"""Фоновые задачи модуля identity (CONV §10)."""

from datetime import timedelta

import structlog

from sportintel.modules.identity.application.login import TX_TTL
from sportintel.modules.identity.infrastructure.repository import SqlOidcTxStore, SqlSessionStore
from sportintel.platform import jobs

PURGE_GRACE = timedelta(days=7)
_log = structlog.get_logger("sportintel.identity")


async def purge_sessions_now() -> int:
    rt = jobs.runtime()
    now = rt.clock.now()
    async with rt.db.uow() as uow:
        removed = await SqlSessionStore(uow.session).purge_expired(now, PURGE_GRACE)
        # OIDC-транзакции живут 10 мин (BE-T0.15 §8): чистятся той же задачей.
        txs = await SqlOidcTxStore(uow.session).purge_older_than(now - TX_TTL)
    _log.info("identity.sessions_purged", count=removed, oidc_transactions=txs)
    return removed


@jobs.periodic("identity.purge_sessions", cron="7 * * * *")
async def purge_sessions(timestamp: int) -> None:
    await purge_sessions_now()
