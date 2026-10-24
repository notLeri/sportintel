"""structlog: JSON для Cloud Logging или console локально (CONV §7.4)."""

import logging
import sys
from typing import Any

import structlog
from structlog.typing import EventDict, Processor, WrappedLogger

from sportintel.platform.config import Settings


def bind_context(**kv: Any) -> None:
    structlog.contextvars.bind_contextvars(**kv)


def clear_context() -> None:
    structlog.contextvars.clear_contextvars()


def _cloud_fields(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
    event_dict["msg"] = event_dict.pop("event", "")
    event_dict["severity"] = event_dict.pop("level", "info").upper()
    return event_dict


SENSITIVE_KEYS = {"cookie", "authorization", "x-csrf-token", "set-cookie", "csrf_token", "session"}


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: "[redacted]" if str(k).lower() in SENSITIVE_KEYS else _redact(v)
            for k, v in value.items()
        }
    if isinstance(value, list | tuple):
        return type(value)(_redact(v) for v in value)
    return value


def redact_headers(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
    """Значения cookie/Authorization/X-CSRF-Token не попадают в логи (BE-T5.5)."""
    return _redact(event_dict)


def configure_logging(settings: Settings, service: str = "web") -> None:
    """Идемпотентна: повторный вызов заменяет обработчики, а не добавляет."""
    static = {"env": settings.env, "service": service, "version": settings.version}

    def add_static(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
        for k, v in static.items():
            event_dict.setdefault(k, v)
        return event_dict

    shared: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="ts"),
        add_static,
        redact_headers,
    ]
    renderer: Processor
    if settings.log_format == "json":
        shared.append(_cloud_fields)
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        # без кэша: повторная configure_logging (тесты, смена уровня) применяется ко всем логгерам
        cache_logger_on_first_use=False,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.format_exc_info,
                renderer,
            ],
        )
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level.upper())
    # uvicorn пишет через stdlib → тот же форматтер; access-лог заменён RequestIdMiddleware.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True
    logging.getLogger("uvicorn.access").disabled = True
