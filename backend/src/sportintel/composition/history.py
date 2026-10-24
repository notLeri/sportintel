"""История действий (BE-T4.7): аудит + имена пользователей. Composition импортирует только public.py модулей."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from sportintel.modules.audit import public as audit
from sportintel.modules.identity import public as identity
from sportintel.platform.errors import FieldError, ValidationFailed
from sportintel.platform.pagination import decode_cursor, encode_cursor

P = identity.Permission
router = APIRouter(prefix="/api/v1/audit", tags=["audit"], route_class=identity.PermissionedRoute)


class ActorRef(BaseModel):
    id: uuid.UUID
    name: str


class AuditEntryItem(BaseModel):
    id: int
    at: datetime
    actor: ActorRef | None
    action: str
    target_type: str
    target_id: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    reason: str | None


class AuditPage(BaseModel):
    items: list[AuditEntryItem]
    next_cursor: str | None


@router.get("", openapi_extra=identity.route_permission(P.AUDIT_READ))
async def list_audit(
    request: Request,
    _: Annotated[identity.CurrentUser, identity.require(P.AUDIT_READ)],
    event_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> AuditPage:
    if event_id is None and not (target_type and target_id):
        raise ValidationFailed(
            details=[
                FieldError("event_id", "required", "event_id or target_type+target_id is required")
            ]
        )
    after = decode_cursor(cursor, [datetime, int]) if cursor else None
    async with request.app.state.db.uow() as uow:
        rows = await audit.list_entries(
            uow,
            context_event_id=event_id,
            target_type=None if event_id else target_type,
            target_id=None if event_id else target_id,
            after=after,
            limit=limit + 1,
        )
        page = rows[:limit]
        names = await identity.user_names(uow, {r["actor_id"] for r in page if r["actor_id"]})
    items = [
        AuditEntryItem(
            **{
                k: r[k]
                for k in (
                    "id",
                    "at",
                    "action",
                    "target_type",
                    "target_id",
                    "before",
                    "after",
                    "reason",
                )
            },
            actor=ActorRef(id=r["actor_id"], name=names.get(r["actor_id"], "—"))
            if r["actor_id"]
            else None,
        )
        for r in page
    ]
    nxt = encode_cursor([page[-1]["at"], page[-1]["id"]]) if len(rows) > limit else None
    return AuditPage(items=items, next_cursor=nxt)
