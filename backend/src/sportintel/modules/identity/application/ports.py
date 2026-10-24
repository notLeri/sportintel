"""Порты модуля identity: реализации — в infrastructure, связывание — public.py/api."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sportintel.modules.identity.domain.access_policy import OidcIdentity
from sportintel.modules.identity.domain.user import User
from sportintel.modules.identity.domain.values import Role


class OidcError(Exception):
    """Сбой IdP: сеть, таймаут, невалидный ответ или id_token."""


class OidcProvider(Protocol):
    async def build_authorize_url(
        self, state: str, nonce: str, code_verifier: str, redirect_uri: str
    ) -> str: ...

    async def exchange_code(
        self, code: str, code_verifier: str, redirect_uri: str, nonce: str
    ) -> OidcIdentity: ...

    async def end_session_url(self) -> str | None: ...


@dataclass(frozen=True)
class OidcTransaction:
    tx_id: str
    state: str
    nonce: str
    code_verifier: str
    next_path: str
    created_at: datetime


class OidcTxStore(Protocol):
    async def insert(self, tx: OidcTransaction) -> None: ...
    async def pop(self, tx_id: str) -> OidcTransaction | None: ...


class UserStore(Protocol):
    async def find_by_subject(self, subject: str) -> User | None: ...
    async def find_by_email(self, email: str) -> User | None: ...
    async def any_active_admin(self) -> bool: ...
    async def insert(self, user: User) -> None: ...
    async def record_login(
        self, user_id: uuid.UUID, *, subject: str, email: str, display_name: str, at: datetime
    ) -> User: ...


__all__ = ["OidcError", "OidcProvider", "OidcTransaction", "OidcTxStore", "Role", "UserStore"]
