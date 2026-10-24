"""Composition root worker-процесса: регистрирует задачи и запускает очереди CONV §10."""

import asyncio
import signal
from collections.abc import Iterable

import structlog

from sportintel.composition import tasks as _tasks  # noqa: F401 — регистрация задач
from sportintel.platform import jobs
from sportintel.platform.clock import SystemClock
from sportintel.platform.config import Settings, load_settings_or_exit
from sportintel.platform.db import Database
from sportintel.platform.logging import configure_logging
from sportintel.platform.safe_fetch import PoliteFetcher, SafeHttpFetcher
from sportintel.platform.telemetry import init_telemetry

SHUTDOWN_GRACEFUL_TIMEOUT_S = 50
_log = structlog.get_logger("sportintel.worker")


async def _health(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    # Cloud Run требует, чтобы сервис слушал PORT; содержимое запроса не важно.
    writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok")
    try:
        await writer.drain()
    finally:
        writer.close()


async def _run_worker(name: str, queues: Iterable[str], concurrency: int) -> None:
    await jobs.JOBS.run_worker_async(
        name=name,
        queues=list(queues),
        concurrency=concurrency,
        install_signal_handlers=False,  # сигналы обрабатывает serve(): воркеров несколько
        shutdown_graceful_timeout=SHUTDOWN_GRACEFUL_TIMEOUT_S,
    )


async def serve(settings: Settings) -> None:
    db = Database(settings.database_url, settings.db_pool_size)
    clock = SystemClock()
    safe = SafeHttpFetcher(
        user_agent=settings.fetch_user_agent or "SportIntelBot/1.0",
        allow_hosts=frozenset(settings.safe_fetch_allow_hosts),
        allow_fake_ip=settings.safe_fetch_allow_fake_ip,
    )
    jobs.set_runtime(db, clock, fetcher=PoliteFetcher(safe, db, clock))
    await jobs.open(
        settings.database_url,
        max_size=settings.worker_concurrency
        + settings.worker_interactive_concurrency
        + settings.worker_fetch_concurrency
        + settings.ollama_concurrency
        + 4,
    )
    health = await asyncio.start_server(_health, "0.0.0.0", settings.port)  # noqa: S104

    workers = [
        asyncio.create_task(
            _run_worker("worker-main", jobs.main_queues(), settings.worker_concurrency)
        ),
        asyncio.create_task(
            _run_worker("worker-fetch", [jobs.FETCH_QUEUE], settings.worker_fetch_concurrency)
        ),
        asyncio.create_task(
            _run_worker("worker-translate", [jobs.TRANSLATE_QUEUE], settings.ollama_concurrency)
        ),
        asyncio.create_task(
            _run_worker(
                "worker-interactive",
                [jobs.INTERACTIVE_QUEUE],
                settings.worker_interactive_concurrency,
            )
        ),
    ]
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    _log.info("platform.worker_started", queues=list(jobs.QUEUES))

    stop_wait = asyncio.create_task(stop.wait())
    await asyncio.wait([*workers, stop_wait], return_when=asyncio.FIRST_COMPLETED)
    _log.info("platform.worker_stopping")
    # Отмена → Procrastinate перестаёт брать задачи и ждёт текущие до shutdown_graceful_timeout.
    for w in [*workers, stop_wait]:
        w.cancel()
    results = await asyncio.gather(*workers, return_exceptions=True)
    for r in results:
        if isinstance(r, Exception):
            _log.error("platform.worker_crashed", exc_info=r)
    health.close()
    await health.wait_closed()
    await jobs.close()
    await db.dispose()
    _log.info("platform.worker_stopped")


def run() -> None:
    settings = load_settings_or_exit()
    configure_logging(settings, service="worker")
    init_telemetry(settings, "worker")  # до Procrastinate: иначе ошибки задач не перехватятся
    asyncio.run(serve(settings))
