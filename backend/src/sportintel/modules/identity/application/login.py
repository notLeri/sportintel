"""OIDC Authorization Code + PKCE (BE-T0.15)."""

import secrets
from dataclasses import dataclass
from datetime import timedelta

import structlog

from sportintel.modules.identity.application.ports import (
    OidcProvider,
    OidcTransaction,
    OidcTxStore,
    UserStore,
)
from sportintel.modules.identity.application.sessions import (
    CurrentUser,
    SessionStore,
    create_session,
    to_current_user,
)
from sportintel.modules.identity.domain.access_policy import (
    Deny,
    DenyCode,
    OidcIdentity,
    decide_access,
    sanitize_next,
)
from sportintel.modules.identity.domain.user import DEFAULT_TIMEZONE, User
from sportintel.modules.identity.domain.values import Locale
from sportintel.platform.clock import Clock
from sportintel.platform.db import UnitOfWork
from sportintel.platform.ids import new_id

TX_TTL = timedelta(minutes=10)
_log = structlog.get_logger("sportintel.identity")


@dataclass(frozen=True)
class LoginConfig:
    allowed_domains: frozenset[str]
    bootstrap_admin_email: str | None


class AccessDenied(Exception):
    def __init__(self, code: DenyCode) -> None:
        super().__init__(code)
        self.code = code


async def start_login(
    txs: OidcTxStore, provider: OidcProvider, next_raw: str | None, redirect_uri: str, clock: Clock
) -> tuple[str, str]:
    """→ (tx_id для cookie oidc_tx, authorize URL)."""
    tx = OidcTransaction(
        tx_id=secrets.token_urlsafe(24),
        state=secrets.token_urlsafe(24),
        nonce=secrets.token_urlsafe(24),
        code_verifier=secrets.token_urlsafe(48),  # 64 символа: в пределах 43–128 RFC 7636
        next_path=sanitize_next(next_raw),
        created_at=clock.now(),
    )
    await txs.insert(tx)
    url = await provider.build_authorize_url(tx.state, tx.nonce, tx.code_verifier, redirect_uri)
    return tx.tx_id, url


async def consume_transaction(
    txs: OidcTxStore, tx_id: str | None, state: str | None, clock: Clock
) -> OidcTransaction | None:
    """Транзакция одноразовая: удаляется при любом исходе проверки."""
    if not tx_id or not state:
        return None
    tx = await txs.pop(tx_id)
    if tx is None or clock.now() - tx.created_at > TX_TTL:
        return None
    return tx if secrets.compare_digest(tx.state, state) else None


async def complete_login(
    uow: UnitOfWork,
    users: UserStore,
    sessions: SessionStore,
    identity: OidcIdentity,
    ip: str | None,
    user_agent: str | None,
    clock: Clock,
    config: LoginConfig,
) -> tuple[str, CurrentUser]:
    existing = await users.find_by_subject(identity.subject) or await users.find_by_email(
        identity.email
    )
    decision = decide_access(
        identity,
        existing,
        set(config.allowed_domains),
        config.bootstrap_admin_email,
        await users.any_active_admin(),
    )
    if isinstance(decision, Deny):
        if decision.subject_mismatch:
            _log.warning(
                "identity.subject_mismatch", user_id=str(existing.id) if existing else None
            )
        _log.info("identity.login_denied", code=decision.code)
        raise AccessDenied(decision.code)

    now = clock.now()
    display_name = identity.name or identity.email.split("@", 1)[0]
    if existing is None:
        assert decision.role_for_new_user is not None  # noqa: S101 — инвариант decide_access
        user = User(
            id=new_id(),
            email=identity.email,
            display_name=display_name,
            role=decision.role_for_new_user,
            locale=Locale.RU,
            timezone=DEFAULT_TIMEZONE,
            hotkeys_enabled=True,
            active=True,
            invited=False,
            oidc_subject=identity.subject,
            last_login_at=now,
            version=1,
        )
        await users.insert(user)
    else:
        # Смена email в IdP: пользователь найден по subject, email обновляется.
        user = await users.record_login(
            existing.id,
            subject=identity.subject,
            email=identity.email,
            display_name=display_name,
            at=now,
        )
    token, record = await create_session(uow, sessions, user.id, ip, user_agent, clock)
    _log.info("identity.login_succeeded", user_id=str(user.id), new_user=existing is None)
    return token, to_current_user(user, record)
