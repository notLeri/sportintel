"""Sentry для web, worker и migrate (BE-T0.13). Пустой SENTRY_DSN — телеметрия выключена."""

import logging
from typing import Any, Literal

import sentry_sdk
import structlog
from sentry_sdk.integrations.asyncio import AsyncioIntegration
from sentry_sdk.integrations.logging import LoggingIntegration, ignore_logger

from sportintel.platform.config import Settings
from sportintel.platform.errors import DomainError

Service = Literal["web", "worker", "migrate"]
_SENSITIVE_HEADERS = {"cookie", "authorization", "x-csrf-token"}
_log = structlog.get_logger("sportintel.telemetry")


def scrub_event(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    """before_send: без PII и секретов; 4xx-доменные ошибки — не инциденты (CONV §15.6)."""
    exc_info = hint.get("exc_info")
    if exc_info and isinstance(exc_info[1], DomainError) and exc_info[1].http_status < 500:
        return None

    request = event.get("request")
    if isinstance(request, dict):
        headers = request.get("headers")
        if isinstance(headers, dict):
            request["headers"] = {
                k: v for k, v in headers.items() if k.lower() not in _SENSITIVE_HEADERS
            }
        request.pop("cookies", None)
        request.pop("data", None)
    user = event.get("user")
    if isinstance(user, dict):
        user.pop("email", None)

    tags = event.setdefault("tags", {})
    ctx = structlog.contextvars.get_contextvars()
    for key in ("request_id", "job_id"):
        if ctx.get(key) is not None:
            tags[key] = str(ctx[key])
    # Ошибка задачи логирует Procrastinate уже вне нашего контекста — id из extra записи.
    job = (event.get("extra") or {}).get("job")
    if isinstance(job, dict) and "job_id" not in tags and job.get("id") is not None:
        tags["job_id"] = str(job["id"])
    return event


def init_telemetry(settings: Settings, service: Service) -> bool:
    if settings.sentry_dsn is None or not settings.sentry_dsn.get_secret_value():
        _log.info("telemetry.disabled", service=service)
        return False
    sentry_sdk.init(
        dsn=settings.sentry_dsn.get_secret_value(),
        environment=settings.env,
        release=settings.version,
        server_name=service,
        send_default_pii=False,
        traces_sample_rate=0.0,  # performance выключен в MVP (BE-T0.13 §23)
        before_send=scrub_event,  # type: ignore[arg-type]
        integrations=[
            AsyncioIntegration(),
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
    )
    # Исключение 500 уже отправляет интеграция FastAPI; лог http.unhandled_exception — дубль.
    ignore_logger("sportintel.http")
    _log.info("telemetry.enabled", service=service)
    return True
