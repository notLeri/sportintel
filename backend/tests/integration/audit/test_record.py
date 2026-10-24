import uuid

import pytest
import structlog
from sqlalchemy import text

from sportintel.modules.audit import public as audit
from sportintel.platform.db import Database


async def rows(db: Database, target: str) -> list[dict]:  # type: ignore[type-arg]
    async with db.uow() as u:
        res = await u.session.execute(
            text("SELECT * FROM audit.audit_log WHERE target_id = :t"), {"t": target}
        )
        return [dict(r._mapping) for r in res]


async def test_record_in_transaction_with_request_id(db: Database) -> None:
    target = str(uuid.uuid4())
    structlog.contextvars.bind_contextvars(request_id="req-123")
    try:
        async with db.uow() as u:
            await audit.record(
                u,
                actor_id=None,
                action=audit.AuditAction.SOURCE_UPDATED,
                target_type="source",
                target_id=target,
                before={"a": 1},
                after={"a": 2},
                reason="teste",
            )
    finally:
        structlog.contextvars.unbind_contextvars("request_id")
    [r] = await rows(db, target)
    assert (r["action"], r["after"], r["request_id"], r["actor_id"]) == (
        "source.updated",
        {"a": 2},
        "req-123",
        None,
    )


async def _failing_action(db: Database, target: str) -> None:
    async with db.uow() as u:
        await audit.record(
            u,
            actor_id=None,
            action=audit.AuditAction.DRAFT_SAVED,
            target_type="draft",
            target_id=target,
        )
        raise RuntimeError("boom")


async def test_rollback_drops_audit_and_unknown_action_fails(db: Database) -> None:
    target = str(uuid.uuid4())
    with pytest.raises(RuntimeError):
        await _failing_action(db, target)
    assert await rows(db, target) == []
    with pytest.raises(TypeError):
        async with db.uow() as u:
            await audit.record(
                u, actor_id=None, action="draft.whatever", target_type="draft", target_id=target
            )  # type: ignore[arg-type]
