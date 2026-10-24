import uuid
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, exists, insert, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from sportintel.modules.identity.application.ports import OidcTransaction
from sportintel.modules.identity.domain.session import SessionRecord
from sportintel.modules.identity.domain.user import User
from sportintel.modules.identity.domain.values import Locale, Role
from sportintel.modules.identity.infrastructure.tables import oidc_transactions, sessions, users


def user_from_row(m: Mapping[str, Any]) -> User:
    return User(
        id=m["id"],
        email=m["email"],
        display_name=m["display_name"],
        role=Role(m["role"]),
        locale=Locale(m["locale"]),
        timezone=m["timezone"],
        hotkeys_enabled=m["hotkeys_enabled"],
        active=m["active"],
        invited=m["invited"],
        oidc_subject=m["oidc_subject"],
        last_login_at=m["last_login_at"],
        version=m["version"],
    )


# Хэш пароля не нужен проверке сессии на каждый запрос — читается только при входе.
_USER_FIELDS = [c for c in users.c if c.name != "password_hash"]
_USER_COLS = [c.label(f"u_{c.name}") for c in _USER_FIELDS]


class SqlSessionStore:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def insert(self, record: SessionRecord, ip: str | None, user_agent: str | None) -> None:
        await self.session.execute(
            insert(sessions).values(
                id_hash=record.id_hash,
                user_id=record.user_id,
                csrf_token=record.csrf_token,
                created_at=record.created_at,
                last_seen_at=record.last_seen_at,
                idle_expires_at=record.idle_expires_at,
                absolute_expires_at=record.absolute_expires_at,
                ip=ip,
                user_agent=user_agent,
            )
        )

    async def get_with_active_user(self, id_hash: bytes) -> tuple[SessionRecord, User] | None:
        row = (
            await self.session.execute(
                select(sessions, *_USER_COLS)
                .join(users, users.c.id == sessions.c.user_id)
                .where(sessions.c.id_hash == id_hash, users.c.active.is_(True))
            )
        ).first()
        if row is None:
            return None
        m = row._mapping
        record = SessionRecord(
            id_hash=m["id_hash"],
            user_id=m["user_id"],
            csrf_token=m["csrf_token"],
            created_at=m["created_at"],
            last_seen_at=m["last_seen_at"],
            idle_expires_at=m["idle_expires_at"],
            absolute_expires_at=m["absolute_expires_at"],
        )
        return record, user_from_row({c.name: m[f"u_{c.name}"] for c in _USER_FIELDS})

    async def touch(self, record: SessionRecord) -> None:
        await self.session.execute(
            update(sessions)
            .where(sessions.c.id_hash == record.id_hash)
            .values(last_seen_at=record.last_seen_at, idle_expires_at=record.idle_expires_at)
        )

    async def delete(self, id_hash: bytes) -> None:
        await self.session.execute(delete(sessions).where(sessions.c.id_hash == id_hash))

    async def delete_for_user(self, user_id: uuid.UUID) -> int:
        result = await self.session.execute(delete(sessions).where(sessions.c.user_id == user_id))
        return int(result.rowcount or 0)  # type: ignore[attr-defined]

    async def purge_expired(self, now: datetime, grace: timedelta) -> int:
        cutoff = now - grace
        result = await self.session.execute(
            delete(sessions).where(
                or_(sessions.c.absolute_expires_at < cutoff, sessions.c.idle_expires_at < cutoff)
            )
        )
        return int(result.rowcount or 0)  # type: ignore[attr-defined]


class SqlUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def insert(self, user: User) -> None:
        await self.session.execute(
            insert(users).values(
                id=user.id,
                email=user.email,
                display_name=user.display_name,
                role=user.role.value,
                locale=user.locale.value,
                timezone=user.timezone,
                hotkeys_enabled=user.hotkeys_enabled,
                active=user.active,
                invited=user.invited,
                oidc_subject=user.oidc_subject,
                last_login_at=user.last_login_at,
                version=user.version,
            )
        )

    async def get(self, user_id: uuid.UUID) -> User | None:
        row = (await self.session.execute(select(users).where(users.c.id == user_id))).first()
        return user_from_row(dict(row._mapping)) if row else None

    async def set_role_and_login(self, user_id: uuid.UUID, role: Role, at: datetime) -> User:
        row = (
            await self.session.execute(
                update(users)
                .where(users.c.id == user_id)
                .values(
                    role=role.value,
                    active=True,
                    last_login_at=at,
                    updated_at=at,
                    version=users.c.version + 1,
                )
                .returning(*users.c)
            )
        ).one()
        return user_from_row(dict(row._mapping))

    async def set_active(self, user_id: uuid.UUID, active: bool) -> None:
        await self.session.execute(update(users).where(users.c.id == user_id).values(active=active))

    async def find_by_subject(self, subject: str) -> User | None:
        row = (
            await self.session.execute(select(users).where(users.c.oidc_subject == subject))
        ).first()
        return user_from_row(dict(row._mapping)) if row else None

    async def find_by_email(self, email: str) -> User | None:
        row = (await self.session.execute(select(users).where(users.c.email == email))).first()
        return user_from_row(dict(row._mapping)) if row else None

    async def find_with_password(self, email: str) -> tuple[User, str | None] | None:
        row = (await self.session.execute(select(users).where(users.c.email == email))).first()
        if row is None:
            return None
        m = dict(row._mapping)
        return user_from_row(m), m["password_hash"]

    async def set_password(self, user_id: uuid.UUID, password_hash: str, at: datetime) -> None:
        await self.session.execute(
            update(users)
            .where(users.c.id == user_id)
            .values(password_hash=password_hash, updated_at=at, version=users.c.version + 1)
        )

    async def touch_login(self, user_id: uuid.UUID, at: datetime) -> None:
        await self.session.execute(
            update(users).where(users.c.id == user_id).values(last_login_at=at, invited=False)
        )

    async def any_active_admin(self) -> bool:
        q = select(exists().where(users.c.role == "admin", users.c.active.is_(True)))
        return bool((await self.session.execute(q)).scalar())

    async def record_login(
        self, user_id: uuid.UUID, *, subject: str, email: str, display_name: str, at: datetime
    ) -> User:
        row = (
            await self.session.execute(
                update(users)
                .where(users.c.id == user_id)
                .values(
                    oidc_subject=subject,
                    email=email,
                    display_name=display_name,
                    last_login_at=at,
                    updated_at=at,
                    version=users.c.version + 1,
                )
                .returning(*users.c)
            )
        ).one()
        return user_from_row(dict(row._mapping))


class SqlOidcTxStore:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def insert(self, tx: OidcTransaction) -> None:
        await self.session.execute(
            insert(oidc_transactions).values(
                tx_id=tx.tx_id,
                state=tx.state,
                nonce=tx.nonce,
                code_verifier=tx.code_verifier,
                next_path=tx.next_path,
                created_at=tx.created_at,
            )
        )

    async def pop(self, tx_id: str) -> OidcTransaction | None:
        row = (
            await self.session.execute(
                delete(oidc_transactions)
                .where(oidc_transactions.c.tx_id == tx_id)
                .returning(*oidc_transactions.c)
            )
        ).first()
        return OidcTransaction(**dict(row._mapping)) if row else None

    async def purge_older_than(self, cutoff: datetime) -> int:
        result = await self.session.execute(
            delete(oidc_transactions).where(oidc_transactions.c.created_at < cutoff)
        )
        return int(result.rowcount or 0)  # type: ignore[attr-defined]
