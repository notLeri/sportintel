"""Админка источников (BE-T4.8): пробный fetch и статистика — склейка sources и ingestion."""

import uuid
from datetime import datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from sportintel.modules.identity import public as identity
from sportintel.modules.ingestion import public as ingestion
from sportintel.modules.sources import public as sources
from sportintel.platform.db import Database
from sportintel.platform.errors import FieldError, NotFound, ValidationFailed

P = identity.Permission
router = APIRouter(
    prefix="/api/v1/sources", tags=["sources"], route_class=identity.PermissionedRoute
)
PERM = identity.route_permission(P.SOURCES_MANAGE)
Admin = Annotated[identity.CurrentUser, identity.require(P.SOURCES_MANAGE)]


class TestStarted(BaseModel):
    test_id: uuid.UUID


class SourceTestResult(BaseModel):
    id: uuid.UUID
    status: str
    feeds: list[dict[str, Any]]
    sample: dict[str, Any] | None
    created_at: datetime


@router.post("/{source_id}:test", status_code=202, openapi_extra=PERM)
async def start_test(source_id: uuid.UUID, request: Request, user: Admin) -> TestStarted:
    async with request.app.state.db.uow() as uow:
        meta = await sources.get_source_meta(uow, source_id)
        if meta.kind == "manual":
            raise ValidationFailed(
                details=[FieldError("kind", "not_testable", "manual sources have no feeds")]
            )
        return TestStarted(test_id=await ingestion.start_preview(uow, source_id, user.id))


@router.get("/tests/{test_id}", openapi_extra=PERM)
async def get_test(test_id: uuid.UUID, request: Request, _: Admin) -> SourceTestResult:
    async with request.app.state.db.uow() as uow:
        row = await ingestion.get_preview(uow, test_id)
    if row is None:
        raise NotFound(f"source test {test_id} not found")
    result = row["result"] or {}
    return SourceTestResult(
        id=row["id"],
        status=row["status"],
        feeds=result.get("feeds", []),
        sample=result.get("sample"),
        created_at=row["created_at"],
    )


def articles_24h(state: Any) -> Any:
    """db/clock читаются при вызове: тесты подменяют их после создания приложения."""

    async def counts() -> dict[uuid.UUID, int]:
        db: Database = state.db
        async with db.uow() as uow:
            return await ingestion.count_recent_by_source(
                uow, state.clock.now() - timedelta(hours=24)
            )

    return counts
