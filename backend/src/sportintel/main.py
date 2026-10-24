"""Composition root web-процесса (ARCHITECTURE §5)."""

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from sportintel.composition import (
    ai_load,
    channel_feed,
    history,
    pipeline,
    sources_admin,
    system_status,
)
from sportintel.composition import settings as settings_api
from sportintel.composition import tasks as _tasks  # noqa: F401 — регистрация задач
from sportintel.modules.analytics import public as analytics
from sportintel.modules.editorial import public as editorial
from sportintel.modules.events import public as events
from sportintel.modules.identity import public as identity
from sportintel.modules.ingestion import public as ingestion
from sportintel.modules.intelligence import public as intelligence
from sportintel.modules.sources import public as sources
from sportintel.modules.taxonomy import public as taxonomy
from sportintel.platform import jobs
from sportintel.platform.clock import SystemClock
from sportintel.platform.config import Settings, enabled_flags, get_settings, load_settings_or_exit
from sportintel.platform.db import Database, head_revision
from sportintel.platform.flags import warn_unknown_flags
from sportintel.platform.http_api import (
    PROBLEM_RESPONSES,
    CsrfMiddleware,
    RequestIdMiddleware,
    install_error_handlers,
)
from sportintel.platform.logging import configure_logging
from sportintel.platform.security_headers import SecurityHeadersMiddleware
from sportintel.platform.static import mount_spa
from sportintel.platform.telemetry import init_telemetry

_PUBLIC = {"x-permission": "public"}
_DOCS_ENVS = {"local", "ci", "e2e", "staging"}


class HealthStatus(BaseModel):
    status: str
    version: str


class ReadinessStatus(BaseModel):
    status: str
    db: str
    migrations: str
    revision: str | None = None


MIGRATIONS_CHECK_TTL_S = 30.0


class _MigrationsCheck:
    """Кэш сравнения ревизии БД с head скрипта на 30 с (BE-T0.3 §14)."""

    def __init__(self, db: Database) -> None:
        self._db = db
        self._head = head_revision()
        self._checked_at = -MIGRATIONS_CHECK_TTL_S
        self._revision: str | None = None

    async def revision_if_current(self) -> tuple[bool, str | None]:
        if time.monotonic() - self._checked_at >= MIGRATIONS_CHECK_TTL_S:
            self._revision = await self._db.current_revision()
            self._checked_at = time.monotonic()
        return self._revision == self._head, self._revision


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings, service="web")
    init_telemetry(settings, "web")

    # Engine ленивый: соединение открывается при первом запросе, web стартует и без БД.
    db = Database(settings.database_url, settings.db_pool_size)
    migrations = _MigrationsCheck(db)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # Web ставит задачи (enqueue_after_commit, брифы по кнопке): без открытого App они терялись.
        await jobs.open(settings.database_url, max_size=2)
        try:
            if await identity.ensure_initial_admin(db, settings, app.state.clock):
                structlog.get_logger("sportintel.main").info(
                    "identity.initial_admin_created", email=settings.bootstrap_admin_email
                )
        except Exception:  # БД ещё не готова: web поднимется, повтор — при рестарте
            structlog.get_logger("sportintel.main").exception("identity.initial_admin_failed")
        try:
            yield
        finally:
            await jobs.close()
            await db.dispose()

    docs = settings.env in _DOCS_ENVS
    app = FastAPI(
        title="SportIntel API",
        version=settings.version,
        lifespan=lifespan,
        openapi_url="/api/v1/openapi.json" if docs else None,
        docs_url="/api/v1/docs" if docs else None,
        redoc_url=None,
        # Все ошибки — problem+json (CONV §5.2); заменяет HTTPValidationError FastAPI.
        responses=PROBLEM_RESPONSES,
    )
    app.state.db = db
    app.state.settings = settings
    app.state.clock = SystemClock()
    app.state.oidc = identity.build_oidc_provider(settings)
    app.state.known_parser_profiles = lambda: frozenset(ingestion.parser_profiles())

    async def enrichment_for_articles(ids: list[Any]) -> dict[Any, tuple[str | None, str]]:
        # Склейка модулей для API — в composition root, не JOIN по чужим схемам (BE-T1.11 §12).
        async with app.state.db.uow() as uow:
            got = await intelligence.get_enrichments(uow, ids)
        return {k: (v.sport_id, v.relevance) for k, v in got.items()}

    app.state.enrichment_for_articles = enrichment_for_articles

    async def event_ids_for_articles(ids: list[Any]) -> dict[Any, Any]:
        async with app.state.db.uow() as uow:
            return await events.event_ids_for_articles(uow, ids)

    app.state.event_ids_for_articles = event_ids_for_articles
    app.state.allowed_transitions_for = events.allowed_transitions_for
    app.state.draft_briefs = editorial.draft_briefs
    app.state.articles_24h = sources_admin.articles_24h(app.state)
    app.state.system_status = lambda: system_status.compute(app.state.db, app.state.settings)
    # Порядок: последний добавленный — внешний. RequestId снаружи, чтобы 403 CSRF имел request_id.
    app.add_middleware(
        CsrfMiddleware,
        resolve=identity.csrf_resolver(app.state),
        cookie_name=identity.cookie_name(settings.env),
    )
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(SecurityHeadersMiddleware, env=settings.env, csp_mode=settings.csp_mode)
    install_error_handlers(app)

    @app.get("/healthz", openapi_extra=_PUBLIC)
    async def healthz() -> HealthStatus:
        return HealthStatus(status="ok", version=settings.version)

    @app.get(
        "/readyz",
        openapi_extra=_PUBLIC,
        responses={200: {"model": ReadinessStatus}, 503: {"model": ReadinessStatus}},
    )
    async def readyz() -> JSONResponse:
        if not await db.ping():
            # ревизию без БД не узнать — «unknown» вместо выдуманного «behind»
            body = {"status": "unavailable", "db": "down", "migrations": "unknown"}
            return JSONResponse(body, status_code=503)
        current, revision = await migrations.revision_if_current()
        if not current:
            body = {"status": "unavailable", "db": "ok", "migrations": "behind"}
            return JSONResponse(body, status_code=503)
        return JSONResponse({"status": "ok", "db": "ok", "migrations": "ok", "revision": revision})

    app.include_router(identity.router)
    app.include_router(identity.me_router)
    app.include_router(identity.users_router)
    app.include_router(sources_admin.router)
    app.include_router(sources.router)
    app.include_router(ingestion.router)
    app.include_router(events.router)
    app.include_router(taxonomy.admin_router)
    app.include_router(taxonomy.router)
    app.include_router(editorial.router)
    app.include_router(editorial.feed_router)
    app.include_router(editorial.briefs_router)
    app.include_router(editorial.channels_router)
    app.include_router(channel_feed.router)
    app.include_router(history.router)
    app.include_router(analytics.router)
    app.include_router(pipeline.router)
    app.include_router(intelligence.router)
    app.include_router(ai_load.router)
    app.include_router(settings_api.router)
    # Двойная защита: Settings запрещает флаг вне local/e2e, а маршрут ещё и не регистрируется.
    if settings.dev_login_enabled and settings.env in {"local", "e2e"}:
        app.include_router(identity.dev_router)

    # Последним: catch-all маршрут SPA не должен перекрывать API.
    spa = mount_spa(app, settings.static_dir, env=settings.env, oidc=app.state.oidc is not None)
    warn_unknown_flags()
    structlog.get_logger("sportintel.main").info(
        "platform.app_started", flags=enabled_flags(), spa=spa
    )
    return app


def run() -> None:
    settings = load_settings_or_exit()
    uvicorn.run(
        create_app(settings),
        host="0.0.0.0",  # noqa: S104 — контейнер Cloud Run
        port=settings.port,
        proxy_headers=True,
        forwarded_allow_ips="*",
        log_config=None,
        access_log=False,
    )
