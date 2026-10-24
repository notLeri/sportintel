"""Use case серверных сессий (BE-T0.14, ARCHITECTURE §11)."""

import hashlib
import secrets
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from sportintel.modules.identity.domain.session import SessionPolicy, SessionRecord
from sportintel.modules.identity.domain.user import User
from sportintel.platform.clock import Clock
from sportintel.platform.db import Database, UnitOfWork

POLICY = SessionPolicy()
CACHE_TTL_S = 30.0


@dataclass(frozen=True)
class CurrentUser:
    id: uuid.UUID
    email: str
    display_name: str
    role: str
    locale: str
    timezone: str
    hotkeys_enabled: bool
    session_id_hash: bytes
    csrf_token: str


class SessionStore(Protocol):
    async def insert(
        self, record: SessionRecord, ip: str | None, user_agent: str | None
    ) -> None: ...
    async def get_with_active_user(self, id_hash: bytes) -> tuple[SessionRecord, User] | None: ...
    async def touch(self, record: SessionRecord) -> None: ...
    async def delete(self, id_hash: bytes) -> None: ...
    async def delete_for_user(self, user_id: uuid.UUID) -> int: ...


StoreFactory = Callable[[UnitOfWork], SessionStore]


def hash_token(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


# ponytail: кэш в памяти процесса без вытеснения — размер = число активных сессий за 30 с;
# при тысячах пользователей — LRU с лимитом. Другие процессы узнают об отзыве ≤ 30 с.
_cache: dict[bytes, tuple[float, CurrentUser, SessionRecord]] = {}


def clear_cache() -> None:
    _cache.clear()


async def create_session(
    uow: UnitOfWork,
    store: SessionStore,
    user_id: uuid.UUID,
    ip: str | None,
    user_agent: str | None,
    clock: Clock,
) -> tuple[str, SessionRecord]:
    token = secrets.token_urlsafe(32)
    now = clock.now()
    idle, absolute = POLICY.expiries(now)
    record = SessionRecord(
        id_hash=hash_token(token),
        user_id=user_id,
        csrf_token=secrets.token_urlsafe(24),
        created_at=now,
        last_seen_at=now,
        idle_expires_at=idle,
        absolute_expires_at=absolute,
    )
    await store.insert(record, ip, user_agent[:512] if user_agent else None)
    return token, record


def to_current_user(user: User, record: SessionRecord) -> CurrentUser:
    return CurrentUser(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role.value,
        locale=user.locale.value,
        timezone=user.timezone,
        hotkeys_enabled=user.hotkeys_enabled,
        session_id_hash=record.id_hash,
        csrf_token=record.csrf_token,
    )


async def resolve_session(
    db: Database, store_for: StoreFactory, token: str, clock: Clock
) -> CurrentUser | None:
    """Токен cookie → текущий пользователь или None (нет, истекла, пользователь неактивен)."""
    id_hash = hash_token(token)
    now = clock.now()
    cached = _cache.get(id_hash)
    if cached and cached[0] > time.monotonic() and POLICY.is_valid(cached[2], now):
        return cached[1]
    _cache.pop(id_hash, None)

    async with db.uow() as uow:
        store = store_for(uow)
        found = await store.get_with_active_user(id_hash)
        if found is None:
            return None
        record, user = found
        if not POLICY.is_valid(record, now):
            return None
        if POLICY.should_touch(record, now):
            record = POLICY.touched(record, now)
            await store.touch(record)
    current = to_current_user(user, record)
    _cache[id_hash] = (time.monotonic() + CACHE_TTL_S, current, record)
    return current


async def revoke_session(store: SessionStore, token: str) -> None:
    id_hash = hash_token(token)
    _cache.pop(id_hash, None)
    await store.delete(id_hash)


async def revoke_all_for_user(store: SessionStore, user_id: uuid.UUID) -> int:
    for key in [k for k, (_, cu, _) in _cache.items() if cu.id == user_id]:
        _cache.pop(key, None)
    return await store.delete_for_user(user_id)
