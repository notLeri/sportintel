import uuid
from collections.abc import Mapping
from typing import Any, Protocol

import structlog

from sportintel.modules.audit.domain.actions import AuditAction
from sportintel.modules.audit.domain.diff import clip, to_json


class AuditStore(Protocol):
    async def insert(self, row: dict[str, Any]) -> None: ...


async def record(
    store: AuditStore,
    *,
    actor_id: uuid.UUID | None,
    action: AuditAction,
    target_type: str,
    target_id: str,
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
    reason: str | None = None,
    context_event_id: uuid.UUID | None = None,
) -> None:
    if not isinstance(action, AuditAction):
        raise TypeError(f"unknown audit action {action!r}")
    ctx = structlog.contextvars.get_contextvars()
    await store.insert(
        {
            "actor_id": actor_id,
            "action": action.value,
            "target_type": target_type,
            "target_id": target_id,
            "before": clip(to_json(before)) if before is not None else None,
            "after": clip(to_json(after)) if after is not None else None,
            "reason": reason,
            "request_id": ctx.get("request_id"),
            "context_event_id": context_event_id,
        }
    )
