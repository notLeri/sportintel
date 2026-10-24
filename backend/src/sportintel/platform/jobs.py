"""Единственная обёртка над Procrastinate (CONV §7.3, §10). Модули не импортируют procrastinate."""

import functools
import re
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Any

import structlog
from procrastinate import App, JobContext, PsycopgConnector
from procrastinate.exceptions import AlreadyEnqueued
from procrastinate.jobs import Job
from procrastinate.retry import BaseRetryStrategy, RetryDecision
from sqlalchemy.engine import make_url

from sportintel.platform.clock import Clock
from sportintel.platform.logging import bind_context, clear_context

_log = structlog.get_logger("sportintel.jobs")
_NAME_RE = re.compile(r"^[a-z_]+\.[a-z_]+$")

QUEUES = ("maintenance", "scheduler", "fetch", "ai", "ai_interactive", "cluster", "translate")
INTERACTIVE_QUEUE = "ai_interactive"
# Свой воркер: politeness-сон в extract не должен держать AI/cluster/служебные задачи.
FETCH_QUEUE = "fetch"
# Свой воркер: фоновый перевод событий ждёт модель по ~30 с и не должен задерживать
# планировщик, разметку статей (ai) и кластеризацию.
TRANSLATE_QUEUE = "translate"
SEARCH_PATH_OPTIONS = "-c search_path=procrastinate,public"

# Каталог CONV §10: задача вне каталога — ошибка регистрации.
KNOWN_TASKS: set[str] = {
    "platform.heartbeat",
    "platform.reconcile",
    "platform.purge_idempotency",
    "platform.purge_old_jobs",
    "platform.purge_ai_runs",
    "platform.health_watch",
    "identity.purge_sessions",
    "sources.schedule_due",
    "ingestion.fetch_source",
    "ingestion.extract_article",
    "ingestion.purge_content",
    "ingestion.purge_fetch_runs",
    "ingestion.preview_fetch",
    "intelligence.enrich_article",
    "intelligence.relink_entities",
    "events.refresh_for_articles",
    "events.detect_conflicts",
    "events.cluster_article",
    "events.refresh_event",
    "events.generate_summary",
    "editorial.autodraft_due",
    "editorial.ai_first_version_due",
    "editorial.generate_draft",
    "editorial.build_brief",
    "editorial.brief_due",
    "editorial.publish_due",
    "editorial.translate_due",
    "editorial.translate_event",
    "analytics.purge_heartbeats",
}

JOBS = App(connector=PsycopgConnector())  # реальный коннектор подставляет open()


class TransientError(Exception):
    """Маркер «повторить». Любое другое исключение — задача failed без retry."""


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int
    exponential_wait_s: int
    retry_exceptions: tuple[type[Exception], ...] = (TransientError,)

    def delay_s(self, exception: BaseException, previous_attempts: int) -> int | None:
        """Задержка до следующей попытки или None — больше не повторять."""
        if not isinstance(exception, self.retry_exceptions):
            return None
        if previous_attempts + 1 >= self.max_attempts:
            return None
        return self.exponential_wait_s * 2**previous_attempts


class _ExponentialRetry(BaseRetryStrategy):
    # Procrastinate трактует exponential_wait=N как N**(attempt+1) с (60 → 60 с, 1 ч, 60 ч);
    # CONV §10 подразумевает базу с удвоением: N, 2N, 4N…
    def __init__(self, policy: RetryPolicy) -> None:
        self.policy = policy

    def get_retry_decision(self, *, exception: BaseException, job: Job) -> RetryDecision | None:
        delay = self.policy.delay_s(exception, job.attempts)  # attempts — предыдущие попытки
        return None if delay is None else RetryDecision(retry_in={"seconds": delay})


def retry_strategy(policy: RetryPolicy | None) -> BaseRetryStrategy | None:
    return _ExponentialRetry(policy) if policy else None


def validate_task_name(name: str) -> None:
    if not _NAME_RE.fullmatch(name):
        raise ValueError(f"invalid task name {name!r}: expected '<module>.<job>'")
    if name not in KNOWN_TASKS:
        raise ValueError(f"task {name!r} is not in the CONV §10 catalog (jobs.KNOWN_TASKS)")


TaskFn = Callable[..., Awaitable[Any]]


def _with_log_context(name: str, fn: TaskFn, pass_context: bool) -> TaskFn:
    @functools.wraps(fn)
    async def run(context: JobContext, **kwargs: Any) -> Any:
        request_id = kwargs.pop("_request_id", None)
        clear_context()
        job_id = context.job.id if context.job else None
        bind_context(job_id=job_id, task=name, **({"request_id": request_id} if request_id else {}))
        try:
            return await (fn(context, **kwargs) if pass_context else fn(**kwargs))
        finally:
            clear_context()

    return run


def task(
    name: str, *, queue: str, retry: RetryPolicy | None = None, pass_context: bool = False
) -> Callable[[TaskFn], TaskFn]:
    validate_task_name(name)
    if queue not in QUEUES:
        raise ValueError(f"unknown queue {queue!r}")

    def decorator(fn: TaskFn) -> TaskFn:
        JOBS.task(name=name, queue=queue, retry=retry_strategy(retry) or False, pass_context=True)(
            _with_log_context(name, fn, pass_context)
        )
        return fn

    return decorator


def periodic(
    name: str, *, cron: str, queue: str = "maintenance", lock: str | None = None
) -> Callable[[TaskFn], TaskFn]:
    """Periodic-задача; функция обязана принимать `timestamp: int` (так требует Procrastinate)."""
    validate_task_name(name)

    def decorator(fn: TaskFn) -> TaskFn:
        registered = JOBS.task(name=name, queue=queue, pass_context=True)(
            _with_log_context(name, fn, pass_context=False)
        )
        JOBS.periodic(cron=cron, periodic_id=name, lock=lock)(registered)
        return fn

    return decorator


async def enqueue(
    name: str,
    *,
    queueing_lock: str | None = None,
    lock: str | None = None,
    schedule_in_seconds: int | None = None,
    priority: int = 0,
    **kwargs: Any,
) -> bool:
    """Поставить задачу вне UoW. False — queueing_lock уже занят (штатно).
    priority — больше раньше (в пределах очереди): клик редактора обгоняет фоновые задачи."""
    options: dict[str, Any] = {"queueing_lock": queueing_lock, "lock": lock, "priority": priority}
    if schedule_in_seconds is not None:
        options["schedule_in"] = {"seconds": schedule_in_seconds}
    # По имени Procrastinate ставит незарегистрированную задачу в очередь `default`, которую
    # никто не слушает, и queueing_lock держит её там навсегда. Поэтому — только из реестра.
    registered = JOBS.tasks.get(name)
    if registered is None:
        raise RuntimeError(
            f"task {name!r} is not registered in this process (import composition.tasks)"
        )
    try:
        await registered.configure(**options).defer_async(**kwargs)
    except AlreadyEnqueued:
        _log.debug("platform.job_already_enqueued", task=name, queueing_lock=queueing_lock)
        return False
    return True


# --- сверка (правила модулей) ---

ReconcileRule = Callable[[Any, Clock], Awaitable[int]]  # (UnitOfWork, Clock) -> обработано
RECONCILE_RULES: dict[str, ReconcileRule] = {}


def register_reconcile_rule(name: str, rule: ReconcileRule) -> None:
    RECONCILE_RULES[name] = rule


# --- подключение ---


def conninfo(database_url: str) -> str:
    """postgresql+psycopg://… → postgresql://… (libpq; unix-сокет Cloud SQL сохраняется)."""
    url = make_url(database_url).set(drivername="postgresql")
    return url.render_as_string(hide_password=False)


_open_ctx: list[Any] = []


async def open(database_url: str, *, max_size: int = 4) -> App:
    connector = PsycopgConnector(
        conninfo=conninfo(database_url),
        kwargs={"options": SEARCH_PATH_OPTIONS},
        min_size=1,
        max_size=max_size,
    )
    ctx = JOBS.replace_connector(connector)
    ctx.__enter__()
    _open_ctx.append(ctx)
    await JOBS.open_async()
    return JOBS


async def close() -> None:
    await JOBS.close_async()
    while _open_ctx:
        _open_ctx.pop().__exit__(None, None, None)


def main_queues() -> Iterable[str]:
    return [q for q in QUEUES if q not in (INTERACTIVE_QUEUE, FETCH_QUEUE, TRANSLATE_QUEUE)]


# --- runtime процесса: задачам нужна БД и часы ---


@dataclass(frozen=True)
class Runtime:
    db: Any  # platform.db.Database (без импорта: db импортирует jobs)
    clock: Clock
    fetcher: Any = None  # platform.safe_fetch.PoliteFetcher — сеть к источникам (BE-T1.6)


_runtime: list[Runtime] = []


def set_runtime(db: Any, clock: Clock, fetcher: Any = None) -> None:
    # ponytail: один runtime на процесс (web или worker); тесты подменяют через set_runtime.
    _runtime[:] = [Runtime(db, clock, fetcher)]


def runtime() -> Runtime:
    if not _runtime:
        raise RuntimeError("jobs runtime is not set (worker.run or test fixture)")
    return _runtime[0]


# --- Экран пайплайна (BE-T4.12): чтение таблицы Procrastinate напрямую, без API воркера ---


@dataclass(frozen=True)
class QueueStat:
    queue: str
    todo: int
    doing: int
    failed_24h: int
    oldest_todo_age_s: int | None


async def queue_stats(session: Any) -> list[QueueStat]:
    from sqlalchemy import text

    rows = await session.execute(
        text(
            "SELECT queue_name, count(*) FILTER (WHERE status = 'todo'), count(*) FILTER (WHERE status = 'doing'),"
            " count(*) FILTER (WHERE status = 'failed' AND coalesce(scheduled_at, now()) > now() - interval '24 hours'),"
            " extract(epoch FROM now() - min(coalesce(scheduled_at, now())) FILTER (WHERE status = 'todo' AND coalesce(scheduled_at, now()) <= now()))::int"
            " FROM procrastinate.procrastinate_jobs GROUP BY queue_name"
        )
    )
    got = {r[0]: QueueStat(r[0], r[1], r[2], r[3], r[4]) for r in rows}
    return [got.get(q, QueueStat(q, 0, 0, 0, None)) for q in QUEUES]


async def failed_jobs(session: Any, after_id: int | None, limit: int) -> list[dict[str, Any]]:
    from sqlalchemy import text

    rows = await session.execute(
        text(
            "SELECT id, task_name, queue_name AS queue, args, attempts, scheduled_at FROM procrastinate.procrastinate_jobs"
            " WHERE status = 'failed' AND (CAST(:a AS bigint) IS NULL OR id < :a) ORDER BY id DESC LIMIT :k"
        ),
        {"a": after_id, "k": limit},
    )
    return [dict(r._mapping) for r in rows]


async def retry_jobs(session: Any, job_ids: list[int]) -> int:
    """Неудачные задачи снова в todo (повтор вручную)."""
    from sqlalchemy import text

    res = await session.execute(
        text(
            "UPDATE procrastinate.procrastinate_jobs SET status = 'todo', scheduled_at = now(), attempts = 0"
            " WHERE id = ANY(:ids) AND status = 'failed'"
        ),
        {"ids": job_ids},
    )
    return int(res.rowcount or 0)


async def raise_priority(session: Any, queueing_lock: str, priority: int) -> None:
    """Уже стоящую в очереди задачу — вперёд (enqueue с тем же queueing_lock вернул False)."""
    from sqlalchemy import text

    await session.execute(
        text(
            "UPDATE procrastinate.procrastinate_jobs SET priority = :p"
            " WHERE queueing_lock = :l AND status = 'todo' AND priority < :p"
        ),
        {"l": queueing_lock, "p": priority},
    )


async def pending_by_task(session: Any, task_names: list[str]) -> dict[str, int]:
    """Сколько задач каждого вида ждут или выполняются (прогресс очередей ИИ)."""
    from sqlalchemy import text

    rows = await session.execute(
        text(
            "SELECT task_name, count(*) FROM procrastinate.procrastinate_jobs"
            " WHERE status IN ('todo', 'doing') AND task_name = ANY(:t) GROUP BY task_name"
        ),
        {"t": task_names},
    )
    return {r[0]: int(r[1]) for r in rows}
