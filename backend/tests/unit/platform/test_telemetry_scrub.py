import structlog

from sportintel.platform import errors
from sportintel.platform.config import Settings
from sportintel.platform.telemetry import init_telemetry, scrub_event


def _event() -> dict:
    return {
        "request": {
            "headers": {
                "Cookie": "sid=1",
                "Authorization": "Bearer x",
                "X-CSRF-Token": "t",
                "Accept": "*/*",
            },
            "cookies": {"sid": "1"},
            "data": {"password": "p"},
        },
        "user": {"id": "u1", "email": "a@b.c"},
    }


def test_sensitive_data_removed_and_request_id_tagged() -> None:
    structlog.contextvars.bind_contextvars(request_id="req-1")
    try:
        out = scrub_event(_event(), {})
    finally:
        structlog.contextvars.clear_contextvars()
    assert out is not None
    assert out["request"]["headers"] == {"Accept": "*/*"}
    assert "cookies" not in out["request"]
    assert "data" not in out["request"]
    assert out["user"] == {"id": "u1"}
    assert out["tags"]["request_id"] == "req-1"


def test_job_id_from_procrastinate_log_extra() -> None:
    out = scrub_event({"extra": {"job": {"id": 42, "task_name": "x.y"}}}, {})
    assert out is not None
    assert out["tags"]["job_id"] == "42"


def test_4xx_domain_error_dropped() -> None:
    err = errors.NotFound()
    assert scrub_event(_event(), {"exc_info": (type(err), err, None)}) is None


def test_5xx_domain_error_kept() -> None:
    err = errors.AiUnavailable()
    assert scrub_event(_event(), {"exc_info": (type(err), err, None)}) is not None


def test_empty_dsn_disables(settings: Settings) -> None:
    assert init_telemetry(settings, "web") is False
