"""Заголовки безопасности на всех ответах и CSP для HTML (BE-T5.5)."""

from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
ASGIApp = Callable[
    [Scope, Callable[[], Awaitable[Message]], Callable[[Message], Awaitable[None]]], Awaitable[None]
]

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' https: data:; "
    "connect-src 'self' https://*.ingest.sentry.io; font-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)
NO_HSTS_ENVS = {"local", "e2e", "ci"}


def headers_for(
    env: str, csp_mode: str, html: bool, report_uri: str | None = None
) -> list[tuple[bytes, bytes]]:
    out = [
        (b"x-content-type-options", b"nosniff"),
        (b"referrer-policy", b"strict-origin-when-cross-origin"),
        (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
        (b"cross-origin-opener-policy", b"same-origin"),
    ]
    if env not in NO_HSTS_ENVS:
        out.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))
    if html:
        # CSP — только для собранного SPA: dev-сервер Vite с inline-скриптами сюда не попадает (§22).
        policy = CSP + (f"; report-uri {report_uri}" if report_uri else "")
        name = (
            b"content-security-policy"
            if csp_mode == "enforce"
            else b"content-security-policy-report-only"
        )
        out.append((name, policy.encode()))
    return out


class SecurityHeadersMiddleware:
    def __init__(
        self, app: ASGIApp, *, env: str, csp_mode: str, report_uri: str | None = None
    ) -> None:
        self.app, self.env, self.csp_mode, self.report_uri = app, env, csp_mode, report_uri

    async def __call__(
        self,
        scope: Scope,
        receive: Callable[[], Awaitable[Message]],
        send: Callable[[Message], Awaitable[None]],
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def wrapped(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                ctype = next((v for k, v in headers if k.lower() == b"content-type"), b"")
                headers += headers_for(
                    self.env, self.csp_mode, ctype.startswith(b"text/html"), self.report_uri
                )
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, wrapped)
