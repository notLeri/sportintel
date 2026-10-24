"""Кто может войти (BE-T0.15 §7). Порядок правил важен."""

from dataclasses import dataclass
from typing import Literal

from sportintel.modules.identity.domain.user import User
from sportintel.modules.identity.domain.values import Role

DenyCode = Literal["auth.email_not_verified", "auth.not_allowed", "auth.user_inactive"]


@dataclass(frozen=True)
class OidcIdentity:
    subject: str
    email: str
    email_verified: bool
    name: str
    hosted_domain: str | None


@dataclass(frozen=True)
class Allow:
    role_for_new_user: Role | None  # None — пользователь уже существует


@dataclass(frozen=True)
class Deny:
    code: DenyCode
    subject_mismatch: bool = False  # для лога identity.subject_mismatch


AccessDecision = Allow | Deny


def email_domain(email: str) -> str:
    return email.rsplit("@", 1)[-1].lower()


def decide_access(
    identity: OidcIdentity,
    existing_user: User | None,
    allowed_domains: set[str],
    bootstrap_admin_email: str | None,
    any_admin_exists: bool,
) -> AccessDecision:
    if not identity.email_verified:
        return Deny("auth.email_not_verified")
    if existing_user is not None:
        if not existing_user.active:
            return Deny("auth.user_inactive")
        # Тот же email, другой subject — адрес переиспользован в IdP: не отдаём чужой аккаунт.
        if existing_user.oidc_subject and existing_user.oidc_subject != identity.subject:
            return Deny("auth.not_allowed", subject_mismatch=True)
        return Allow(None)
    if (
        bootstrap_admin_email
        and identity.email.lower() == bootstrap_admin_email.lower()
        and not any_admin_exists
    ):
        return Allow(Role.ADMIN)
    # Домен — из email, а не из claim `hd` (его нет у не-Workspace аккаунтов).
    if email_domain(identity.email) in {d.lower() for d in allowed_domains}:
        return Allow(Role.RESEARCHER)
    return Deny("auth.not_allowed")


def sanitize_next(raw: str | None) -> str:
    """Только относительный путь приложения: защита от open redirect."""
    if not raw or not raw.startswith("/") or raw.startswith("//") or "\\" in raw:
        return "/"
    return raw
