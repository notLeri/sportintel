import pytest
import structlog
from structlog.testing import capture_logs

from sportintel.platform import jobs
from sportintel.platform.db import Database, UnitOfWork
from sportintel.platform.reconcile import run_reconcile

pytestmark = pytest.mark.integration_commit


async def test_rules_called_and_counts_logged(
    committing_db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[str] = []

    async def requeue_stuck(uow: UnitOfWork, clock: object) -> int:
        seen.append(type(uow).__name__)
        return 7

    async def broken(uow: UnitOfWork, clock: object) -> int:
        raise RuntimeError("rule bug")

    monkeypatch.setattr(
        jobs, "RECONCILE_RULES", {"test.broken": broken, "test.stuck": requeue_stuck}
    )
    with capture_logs() as logs:
        counts = await run_reconcile()

    assert seen == ["UnitOfWork"]  # сломанное правило не мешает следующим
    assert counts == {"test.stuck": 7, "stalled_jobs": 0}
    events = {(e["event"], e.get("rule")) for e in logs}
    assert ("platform.reconcile_rule_completed", "test.stuck") in events
    assert ("platform.reconcile_rule_failed", "test.broken") in events
    structlog.contextvars.clear_contextvars()
