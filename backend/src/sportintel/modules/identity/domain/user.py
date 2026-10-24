import uuid
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sportintel.modules.identity.domain.values import Locale, Role
from sportintel.platform.errors import FieldError, ValidationFailed

DEFAULT_TIMEZONE = "America/Sao_Paulo"


def validate_timezone(tz: str) -> str:
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValidationFailed(
            details=[FieldError("timezone", "invalid", f"unknown time zone {tz!r}")]
        ) from None
    return tz


@dataclass(frozen=True)
class User:
    id: uuid.UUID
    email: str  # как пришёл от IdP; сравнение без регистра обеспечивает citext
    display_name: str
    role: Role
    locale: Locale
    timezone: str
    hotkeys_enabled: bool
    active: bool
    invited: bool
    oidc_subject: str | None
    last_login_at: datetime | None
    version: int
