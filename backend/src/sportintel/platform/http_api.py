import base64
import binascii
import json
import re
import secrets
import time
from collections.abc import Awaitable, Callable
from http.cookies import CookieError, SimpleCookie
from typing import Any

import sentry_sdk
import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from sportintel.platform.errors import (
    CsrfFailed,
    DomainError,
    FieldError,
    PreconditionRequired,
    RateLimited,
    ValidationFailed,
)
from sportintel.platform.ids import new_id
from sportintel.platform.logging import bind_context, clear_context

_REQUEST_ID_RE = re.compile(r"[A-Za-z0-9-]{8,64}")  # покрывает и UUID в каноничной записи
_log = structlog.get_logger("sportintel.http")


def _request_id(scope: Scope) -> str:
    for name, value in scope["headers"]:
        if name == b"x-request-id":
            candidate = value.decode("latin-1")
            if _REQUEST_ID_RE.fullmatch(candidate):
                return candidate
            break
    return str(new_id())


class RequestIdMiddleware:
    """Чистый ASGI: принимает или генерирует X-Request-ID, пишет лог запроса."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _request_id(scope)
        # request.state: обработчик 500 работает в ServerErrorMiddleware снаружи нас (BE-T0.4 §22)
        scope.setdefault("state", {})["request_id"] = request_id
        clear_context()
        bind_context(request_id=request_id)
        # Scope запроса изолирован интеграцией Sentry ASGI; structlog-контекст к моменту
        # отправки события 500 уже очищен (ServerErrorMiddleware снаружи нас).
        sentry_sdk.set_tag("request_id", request_id)
        status = 500
        started = time.perf_counter()

        async def send_with_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message["headers"] = [
                    *message.get("headers", []),
                    (b"x-request-id", request_id.encode()),
                ]
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            _log.info(
                "http.request_completed",
                method=scope["method"],
                path=scope["path"],
                status=status,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            clear_context()


# --- problem+json (RFC 9457, CONV §5.2) ---

PROBLEM_JSON = "application/problem+json"


class ProblemFieldError(BaseModel):
    field: str
    code: str
    message: str


class ProblemDetail(BaseModel):
    """Тело ошибки RFC 9457 (CONV §5.2) — для контракта OpenAPI и TS-типов."""

    type: str
    title: str
    status: int
    code: str
    detail: str
    errors: list[ProblemFieldError]
    request_id: str | None
    current: dict[str, object] | None


_PROBLEM = {
    "model": ProblemDetail,
    "content": {PROBLEM_JSON: {}},
    "description": "Problem (RFC 9457)",
}
PROBLEM_RESPONSES: dict[int | str, dict[str, object]] = {
    422: _PROBLEM,
    "4XX": _PROBLEM,
    "5XX": _PROBLEM,
}
_ERROR_TYPE_BASE = "https://sportintel/errors/"
_LOC_PREFIXES = {"body", "query", "path", "header", "cookie"}
_HTTP_STATUS_CODES = {
    401: "common.unauthenticated",
    403: "common.forbidden",
    404: "common.not_found",
    405: "common.validation_failed",
    413: "common.payload_too_large",
    429: "common.rate_limited",
}
_FALLBACK_500 = (
    b'{"type":"https://sportintel/errors/common.internal","title":"Internal error",'
    b'"status":500,"code":"common.internal","detail":"Internal error","errors":[],'
    b'"request_id":null,"current":null}'
)


def _problem(
    *,
    status: int,
    code: str,
    title: str,
    detail: str,
    request_id: str | None,
    errors: list[FieldError] | None = None,
    extra: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": _ERROR_TYPE_BASE + code,
        "title": title,
        "status": status,
        "code": code,
        "detail": detail,
        "errors": [{"field": e.field, "code": e.code, "message": e.message} for e in errors or []],
        "request_id": request_id,
        "current": None,
        **(extra or {}),
    }
    return JSONResponse(body, status_code=status, media_type=PROBLEM_JSON, headers=headers)


def problem_response(err: DomainError, request_id: str | None) -> JSONResponse:
    headers = {"Retry-After": str(err.retry_after_s)} if isinstance(err, RateLimited) else None
    return _problem(
        status=err.http_status,
        code=err.code,
        title=err.title,
        detail=err.message,
        request_id=request_id,
        errors=err.details,
        extra=err.extra,
        headers=headers,
    )


def _rid(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def _field_path(loc: tuple[Any, ...]) -> str:
    parts = list(loc[1:] if loc and loc[0] in _LOC_PREFIXES else loc)
    return ".".join(str(p) for p in parts)


async def _on_domain_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainError)  # noqa: S101 — гарантирует регистрация обработчика
    return problem_response(exc, _rid(request))


async def _on_validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)  # noqa: S101
    errors = [
        FieldError(field=_field_path(tuple(e["loc"])), code=e["type"], message=e["msg"])
        for e in exc.errors()
    ]
    return _problem(
        status=422,
        code="common.validation_failed",
        title="Validation failed",
        detail="Request validation failed",
        request_id=_rid(request),
        errors=errors,
    )


async def _on_http_exception(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)  # noqa: S101
    status = exc.status_code
    code = _HTTP_STATUS_CODES.get(
        status, "common.internal" if status >= 500 else "common.validation_failed"
    )
    # detail Starlette — стандартная фраза статуса («Not Found», «Method Not Allowed»)
    return _problem(
        status=status,
        code=code,
        title=str(exc.detail),
        detail=str(exc.detail),
        request_id=_rid(request),
        headers=dict(exc.headers) if exc.headers else None,
    )


async def _on_unhandled(request: Request, exc: Exception) -> Response:
    request_id = _rid(request)
    # Работает в ServerErrorMiddleware: RequestIdMiddleware заголовок уже не добавит.
    headers = {"X-Request-ID": request_id} if request_id else None
    try:
        _log.error("http.unhandled_exception", request_id=request_id, exc_info=exc)
        return _problem(
            status=500,
            code="common.internal",
            title="Internal error",
            detail="Internal error",
            request_id=request_id,
            headers=headers,
        )
    except Exception:  # сбой сериализации/логирования — готовые байты (BE-T0.4 §13)
        return Response(_FALLBACK_500, status_code=500, media_type=PROBLEM_JSON, headers=headers)


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _on_domain_error)
    app.add_exception_handler(RequestValidationError, _on_validation_error)
    app.add_exception_handler(StarletteHTTPException, _on_http_exception)
    app.add_exception_handler(Exception, _on_unhandled)


# --- CSRF (CONV §5.1, BE-T0.16) ---

_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
CsrfResolver = Callable[[str], Awaitable[str | None]]  # токен сессии → ожидаемый csrf или None


def _cookie(scope: Scope, name: str) -> str | None:
    for header, value in scope["headers"]:
        if header == b"cookie":
            jar: SimpleCookie = SimpleCookie()
            try:
                jar.load(value.decode("latin-1"))
            except CookieError:
                return None
            morsel = jar.get(name)
            return morsel.value if morsel else None
    return None


def _header(scope: Scope, name: bytes) -> str:
    for header, value in scope["headers"]:
        if header == name:
            return value.decode("latin-1")
    return ""


class CsrfMiddleware:
    """Мутации требуют X-CSRF-Token = csrf_token сессии. Тело запроса не читается.

    Нет сессии → пропуск: ответит 401 зависимость current_user (а не 403).
    Модули platform не видит: резолвер сессии подставляет main.py.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        resolve: CsrfResolver,
        cookie_name: str,
        exempt_paths: frozenset[str] = frozenset(
            {"/auth/callback", "/auth/dev-login", "/auth/password-login"}
        ),
    ) -> None:
        self.app = app
        self.resolve = resolve
        self.cookie_name = cookie_name
        self.exempt_paths = exempt_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] not in _UNSAFE_METHODS
            or scope["path"] in self.exempt_paths
        ):
            await self.app(scope, receive, send)
            return
        token = _cookie(scope, self.cookie_name)
        expected = await self.resolve(token) if token else None
        if expected is not None:
            sent = _header(scope, b"x-csrf-token")
            if not secrets.compare_digest(sent.encode(), expected.encode()):
                request_id = scope.get("state", {}).get("request_id")
                await problem_response(CsrfFailed(), request_id)(scope, receive, send)
                return
        await self.app(scope, receive, send)


# --- оптимистичная блокировка: ETag / If-Match (CONV §5.1) ---

_IF_MATCH_RE = re.compile(r'^\s*(?:W/)?"(\d{1,9})"\s*$')


def etag(version: int) -> str:
    return f'"{version}"'


def parse_if_match(request: Request) -> int:
    """`If-Match: "<version>"` → version. Нет заголовка → 428; мусор → 422."""
    raw = request.headers.get("if-match")
    if raw is None:
        raise PreconditionRequired()
    m = _IF_MATCH_RE.match(raw)
    if not m:
        raise ValidationFailed(
            details=[FieldError("If-Match", "invalid", 'expected If-Match: "<version>"')]
        )
    return int(m.group(1))


# --- keyset-пагинация (CONV §5.1): cursor = base64url(JSON значений ключа сортировки + id) ---

CursorValue = str | int | float | None


def encode_cursor(values: tuple[CursorValue, ...]) -> str:
    raw = json.dumps(list(values), separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str, arity: int) -> tuple[CursorValue, ...]:
    """Невалидный cursor → 422 common.validation_failed (поле cursor)."""
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        values = json.loads(raw)
    except (binascii.Error, ValueError, UnicodeDecodeError):
        values = None
    if not isinstance(values, list) or len(values) != arity:
        raise ValidationFailed(details=[FieldError("cursor", "invalid", "invalid cursor")])
    return tuple(values)
