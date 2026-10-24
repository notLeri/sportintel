from collections.abc import Iterator

import pytest
import sentry_sdk
import structlog
from sqlalchemy import text
from structlog.testing import LogCapture
from tests.conftest import CaptureTransport

from sportintel.platform import jobs
from sportintel.platform import (
    reconcile as _reconcile,  # noqa: F401  (регистрирует platform.heartbeat)
)
from sportintel.platform.db import Database

pytestmark = pytest.mark.integration_commit

jobs.KNOWN_TASKS |= {"testing.noop", "testing.flaky", "testing.always_fails", "testing.crash"}
CALLS: dict[str, int] = {}


@jobs.task("testing.noop", queue="maintenance")
async def noop(n: int) -> None:
    CALLS["noop"] = CALLS.get("noop", 0) + 1


@jobs.task("testing.flaky", queue="maintenance", retry=jobs.RetryPolicy(3, 0))
async def flaky() -> None:
    CALLS["flaky"] = CALLS.get("flaky", 0) + 1
    if CALLS["flaky"] < 3:
        raise jobs.TransientError("not yet")


@jobs.task("testing.always_fails", queue="maintenance", retry=jobs.RetryPolicy(3, 0))
async def always_fails() -> None:
    CALLS["always_fails"] = CALLS.get("always_fails", 0) + 1
    raise jobs.TransientError("never")


@jobs.task("testing.crash", queue="maintenance")
async def crash() -> None:
    raise ValueError("task bug")


@pytest.fixture(autouse=True)
def _reset_calls() -> None:
    CALLS.clear()


@pytest.fixture
def logs() -> Iterator[LogCapture]:
    cap = LogCapture()
    old = structlog.get_config()
    structlog.configure(processors=[structlog.contextvars.merge_contextvars, cap])
    yield cap
    structlog.configure(**old)


async def _jobs(db: Database, task: str) -> list[str]:
    async with db.uow() as u:
        q = text("SELECT status FROM procrastinate.procrastinate_jobs WHERE task_name = :t")
        return list((await u.session.execute(q, {"t": task})).scalars())


async def _work() -> None:
    await jobs.JOBS.run_worker_async(
        queues=["maintenance"], wait=False, install_signal_handlers=False, listen_notify=False
    )


async def test_enqueue_after_commit_only_on_commit(committing_db: Database) -> None:
    async def fail_inside() -> None:
        async with committing_db.uow() as u:
            u.enqueue_after_commit("testing.noop", n=1)
            raise RuntimeError("rollback")

    with pytest.raises(RuntimeError):
        await fail_inside()
    assert await _jobs(committing_db, "testing.noop") == []

    async with committing_db.uow() as u:
        u.enqueue_after_commit("testing.noop", n=2)
    assert await _jobs(committing_db, "testing.noop") == ["todo"]


async def test_enqueue_after_commit_carries_request_id(committing_db: Database) -> None:
    structlog.contextvars.bind_contextvars(request_id="req-12345678")
    try:
        async with committing_db.uow() as u:
            u.enqueue_after_commit("testing.noop", n=3)
    finally:
        structlog.contextvars.clear_contextvars()
    async with committing_db.uow() as u:
        q = text("SELECT args FROM procrastinate.procrastinate_jobs WHERE task_name='testing.noop'")
        args = (await u.session.execute(q)).scalar_one()
    assert args == {"n": 3, "_request_id": "req-12345678"}
    await _work()
    assert CALLS["noop"] == 1  # _request_id снят обёрткой, задача его не получает


async def test_queueing_lock_deduplicates(committing_db: Database) -> None:
    assert await jobs.enqueue("testing.noop", queueing_lock="noop:1", n=1) is True
    assert await jobs.enqueue("testing.noop", queueing_lock="noop:1", n=1) is False
    assert await _jobs(committing_db, "testing.noop") == ["todo"]


async def test_transient_error_retried_until_success(committing_db: Database) -> None:
    await jobs.enqueue("testing.flaky")
    await _work()
    assert CALLS["flaky"] == 3
    assert await _jobs(committing_db, "testing.flaky") == ["succeeded"]


async def test_max_attempts_exhausted_fails(committing_db: Database) -> None:
    await jobs.enqueue("testing.always_fails")
    await _work()
    assert CALLS["always_fails"] == 3
    assert await _jobs(committing_db, "testing.always_fails") == ["failed"]


async def test_heartbeat_logs_with_job_id(committing_db: Database, logs: LogCapture) -> None:
    await jobs.enqueue("platform.heartbeat", timestamp=1_760_000_000)
    await _work()
    beats = [e for e in logs.entries if e["event"] == "platform.heartbeat"]
    assert len(beats) == 1
    assert beats[0]["job_id"]
    assert beats[0]["task"] == "platform.heartbeat"


async def test_task_crash_reaches_sentry_with_job_id(
    committing_db: Database, captured: CaptureTransport
) -> None:
    from sportintel.platform.config import Settings
    from sportintel.platform.telemetry import init_telemetry

    init_telemetry(
        Settings(
            env="ci",
            database_url="postgresql+psycopg://u:p@h/db",
            app_base_url="http://t",
            sentry_dsn="https://k@o0.ingest.sentry.io/1",
        ),
        "worker",
    )
    await jobs.enqueue("testing.crash")
    await _work()
    sentry_sdk.flush()
    crashes = [
        e for e in captured.events if "task bug" in str(e.get("exception") or e.get("logentry"))
    ]
    assert crashes, captured.events
    assert crashes[0]["tags"].get("job_id")
    assert await _jobs(committing_db, "testing.crash") == ["failed"]


async def test_enqueue_unregistered_task_fails_instead_of_default_queue() -> None:
    # Иначе задача молча уходит в очередь `default`, которую воркер не слушает.
    with pytest.raises(RuntimeError, match="not registered"):
        await jobs.enqueue("testing.never_registered")


async def test_purge_old_jobs_keeps_recent_and_failed_longer(committing_db: Database) -> None:
    await jobs.enqueue("testing.noop", n=1)
    await jobs.enqueue("testing.always_fails")
    await _work()

    async def age(task: str, days: int) -> None:
        async with committing_db.uow() as u:
            await u.session.execute(
                text(
                    "UPDATE procrastinate.procrastinate_events SET at = now() - make_interval(days => :d)"
                    " WHERE job_id IN (SELECT id FROM procrastinate.procrastinate_jobs WHERE task_name = :t)"
                ),
                {"d": days, "t": task},
            )

    async def purge() -> None:
        await jobs.enqueue("platform.purge_old_jobs", timestamp=1_760_000_000)
        await _work()

    await age("testing.noop", 8)
    await age("testing.always_fails", 8)
    await purge()
    assert await _jobs(committing_db, "testing.noop") == []  # успешная, старше 7 дней
    assert await _jobs(committing_db, "testing.always_fails") == ["failed"]  # упавшая живёт 30 дней
    await age("testing.always_fails", 31)
    await purge()
    assert await _jobs(committing_db, "testing.always_fails") == []
