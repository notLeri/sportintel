"""Idempotency-Key для POST (CONV §5.1, BE-T1.10): повтор → сохранённый ответ, хранение 24 ч."""

import hashlib
import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from sportintel.platform.db import Database
from sportintel.platform.errors import (
    DomainError,
    FieldError,
    IdempotencyKeyReused,
    ValidationFailed,
)

TTL = timedelta(hours=24)


def body_hash(method: str, path: str, body: Any) -> bytes:
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(f"{method} {path}\n{canonical}".encode()).digest()


def parse_key(request: Request) -> uuid.UUID:
    raw = request.headers.get("idempotency-key")
    try:
        return uuid.UUID(raw or "")
    except ValueError:
        raise ValidationFailed(
            details=[
                FieldError("Idempotency-Key", "required", "Idempotency-Key (UUID) is required")
            ]
        ) from None


@dataclass
class IdemState:
    cached: JSONResponse | None = None
    _store: dict[str, Any] = field(default_factory=dict)

    def store(self, status: int, body: Any) -> JSONResponse:
        self._store = {"status": status, "body": body}
        return JSONResponse(body, status_code=status)


@asynccontextmanager
async def idempotent(
    db: Database, request: Request, user_id: uuid.UUID, body: Any, now: datetime
) -> AsyncIterator[IdemState]:
    """Строка ключа блокируется (FOR UPDATE) до конца обработки: параллельный повтор ждёт."""
    key = parse_key(request)
    digest = body_hash(request.method, request.url.path, body)
    async with db.uow() as uow:
        s = uow.session
        await s.execute(
            text(
                "INSERT INTO platform.idempotency_keys"
                " (user_id, key, method, path, request_hash, created_at)"
                " VALUES (:u, :k, :m, :p, :h, :now) ON CONFLICT DO NOTHING"
            ),
            {
                "u": user_id,
                "k": key,
                "m": request.method,
                "p": request.url.path,
                "h": digest,
                "now": now,
            },
        )
        row = (
            await s.execute(
                text(
                    "SELECT request_hash, response_status, response_body"
                    " FROM platform.idempotency_keys"
                    " WHERE user_id = :u AND key = :k FOR UPDATE"
                ),
                {"u": user_id, "k": key},
            )
        ).one()
        if bytes(row.request_hash) != digest:
            raise IdempotencyKeyReused()
        state = IdemState()
        if row.response_status is not None:
            state.cached = JSONResponse(row.response_body, status_code=row.response_status)
            yield state
            return
        try:
            yield state
        except DomainError:
            # Ошибка не кэшируется: строка ключа удаляется, клиент может повторить.
            await s.execute(
                text("DELETE FROM platform.idempotency_keys WHERE user_id = :u AND key = :k"),
                {"u": user_id, "k": key},
            )
            await uow.commit()
            raise
        if state._store:
            await s.execute(
                text(
                    "UPDATE platform.idempotency_keys SET response_status = :st,"
                    " response_body = CAST(:b AS jsonb) WHERE user_id = :u AND key = :k"
                ),
                {
                    "st": state._store["status"],
                    "b": json.dumps(state._store["body"]),
                    "u": user_id,
                    "k": key,
                },
            )


async def purge_expired(db: Database, now: datetime) -> int:
    async with db.uow() as uow:
        r = await uow.session.execute(
            text("DELETE FROM platform.idempotency_keys WHERE created_at < :t"), {"t": now - TTL}
        )
    return int(r.rowcount or 0)  # type: ignore[attr-defined]
