"""Доменные ошибки (CONV §5.3). Не знают об HTTP: статус — только подсказка для http_api."""

import re
from dataclasses import dataclass
from typing import Any, ClassVar

_CODE_RE = re.compile(r"^[a-z_]+\.[a-z_]+$")


@dataclass(frozen=True)
class FieldError:
    field: str
    code: str
    message: str


class DomainError(Exception):
    code: str  # подклассы задают значением класса; у DomainError/Conflict его нет
    http_status: ClassVar[int] = 500
    title: ClassVar[str] = "Internal error"

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: list[FieldError] | None = None,
        **extra: Any,
    ) -> None:
        resolved = code or getattr(type(self), "code", None)
        if resolved is None or not _CODE_RE.fullmatch(resolved):
            raise ValueError(f"invalid error code {resolved!r}: expected '<area>.<name>'")
        self.code = resolved
        self.message = message or self.title
        self.details = details or []
        self.extra = extra
        super().__init__(self.message)


class ValidationFailed(DomainError):
    code = "common.validation_failed"
    http_status = 422
    title = "Validation failed"


class NotFound(DomainError):
    code = "common.not_found"
    http_status = 404
    title = "Not found"


class Unauthenticated(DomainError):
    code = "common.unauthenticated"
    http_status = 401
    title = "Authentication required"


class Forbidden(DomainError):
    code = "common.forbidden"
    http_status = 403
    title = "Forbidden"


class CsrfFailed(Forbidden):
    code = "common.csrf_failed"
    title = "CSRF token missing or invalid"


class PreconditionRequired(DomainError):
    code = "common.precondition_required"
    http_status = 428
    title = "If-Match header required"


class ConcurrencyConflict(DomainError):
    code = "common.version_conflict"
    http_status = 412
    title = "Resource version mismatch"

    def __init__(
        self, message: str | None = None, *, current: dict[str, Any] | None = None, **kw: Any
    ) -> None:
        # current — уже сериализованное схемой ресурса представление (передаёт роутер)
        super().__init__(message, current=current, **kw)


class IdempotencyKeyReused(DomainError):
    code = "common.idempotency_key_reused"
    http_status = 422
    title = "Idempotency key reused with a different body"


class PayloadTooLarge(DomainError):
    code = "common.payload_too_large"
    http_status = 413
    title = "Payload too large"


class RateLimited(DomainError):
    code = "common.rate_limited"
    http_status = 429
    title = "Too many requests"

    def __init__(self, message: str | None = None, *, retry_after_s: int, **kw: Any) -> None:
        if retry_after_s < 1:
            raise ValueError("retry_after_s must be >= 1")
        super().__init__(message, **kw)
        self.retry_after_s = retry_after_s


class BudgetExhausted(RateLimited):
    code = "ai.budget_exhausted"
    title = "AI daily budget exhausted"


class AiUnavailable(DomainError):
    code = "ai.unavailable"
    http_status = 503
    title = "AI temporarily unavailable"


class Conflict(DomainError):
    """База для доменных 409: подкласс обязан задать `code` (например, event.invalid_transition)."""

    http_status = 409
    title = "Conflict"
