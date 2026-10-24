"""Экран пайплайна (BE-T4.12): сводка, ошибки статей и задач, повтор. Право pipeline.manage."""

import uuid
from datetime import datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field, model_validator

from sportintel.modules.audit import public as audit
from sportintel.modules.editorial import public as editorial
from sportintel.modules.identity import public as identity
from sportintel.modules.ingestion import public as ingestion
from sportintel.modules.sources import public as sources
from sportintel.platform import jobs
from sportintel.platform.pagination import decode_cursor, encode_cursor

P = identity.Permission
router = APIRouter(
    prefix="/api/v1/pipeline", tags=["pipeline"], route_class=identity.PermissionedRoute
)
PERM = identity.route_permission(P.PIPELINE_MANAGE)
Admin = Annotated[identity.CurrentUser, identity.require(P.PIPELINE_MANAGE)]


class QueueStatOut(BaseModel):
    queue: str
    todo: int
    doing: int
    failed_24h: int
    oldest_todo_age_s: int | None


class CodeCount(BaseModel):
    code: str | None
    count: int


class PipelineSummary(BaseModel):
    articles_24h: dict[str, int]
    failures_by_code: list[CodeCount]
    queues: list[QueueStatOut]
    drafts_failed_24h: int
    ingest_lag_p95_s: int | None


class FailedArticleItem(BaseModel):
    id: uuid.UUID
    title: str
    url: str
    source_name: str
    failure_code: str | None
    failure_detail: str | None
    state_changed_at: datetime


class FailedJobItem(BaseModel):
    id: int
    task_name: str
    queue: str
    args: dict[str, Any]
    attempts: int
    scheduled_at: datetime | None


class FailuresPage(BaseModel):
    articles: list[FailedArticleItem] = []
    jobs: list[FailedJobItem] = []
    next_cursor: str | None


class RetryRequest(BaseModel):
    article_ids: list[uuid.UUID] | None = Field(default=None, max_length=500)
    failure_code: str | None = None
    job_ids: list[int] | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def _one(self) -> "RetryRequest":
        if sum(v is not None for v in (self.article_ids, self.failure_code, self.job_ids)) != 1:
            raise ValueError("exactly one of article_ids, failure_code, job_ids")
        return self


class RetryResult(BaseModel):
    retried: int
    remaining: int = 0


@router.get("/summary", openapi_extra=PERM)
async def summary(request: Request, _: Admin) -> PipelineSummary:
    since = request.app.state.clock.now() - timedelta(hours=24)
    async with request.app.state.db.uow() as uow:
        s = await ingestion.failure_summary(uow, since)
        queues = await jobs.queue_stats(uow.session)
        drafts = await editorial.drafts_failed_since(uow, since)
    return PipelineSummary(
        articles_24h=s["states"],
        failures_by_code=[CodeCount(**c) for c in s["failures_by_code"]],
        queues=[QueueStatOut(**vars(q)) for q in queues],
        drafts_failed_24h=drafts,
        ingest_lag_p95_s=s["ingest_lag_p95_s"],
    )


@router.get("/failures", openapi_extra=PERM)
async def failures(
    request: Request,
    _: Admin,
    kind: Literal["articles", "jobs"] = "articles",
    code: str | None = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> FailuresPage:
    async with request.app.state.db.uow() as uow:
        if kind == "jobs":
            after = decode_cursor(cursor, [int])[0] if cursor else None
            rows = await jobs.failed_jobs(uow.session, after, limit + 1)
            page = rows[:limit]
            nxt = encode_cursor([page[-1]["id"]]) if len(rows) > limit else None
            return FailuresPage(jobs=[FailedJobItem(**r) for r in page], next_cursor=nxt)
        after2 = decode_cursor(cursor, [datetime, uuid.UUID]) if cursor else None
        rows = await ingestion.list_failed(uow, code, after2, limit + 1)
        page = rows[:limit]
        metas = await sources.get_sources_meta(uow, {r["source_id"] for r in page})
    nxt = (
        encode_cursor([page[-1]["state_changed_at"], page[-1]["id"]]) if len(rows) > limit else None
    )
    return FailuresPage(
        articles=[
            FailedArticleItem(
                **{k: v for k, v in r.items() if k != "source_id"},
                source_name=metas[r["source_id"]].name if r["source_id"] in metas else "",
            )
            for r in page
        ],
        next_cursor=nxt,
    )


@router.post("/failures:retry", openapi_extra=PERM)
async def retry(body: RetryRequest, request: Request, user: Admin) -> RetryResult:
    state = request.app.state
    async with state.db.uow() as uow:
        if body.job_ids is not None:
            n, rest = await jobs.retry_jobs(uow.session, body.job_ids), 0
        else:
            n, rest = await ingestion.retry_failed(
                uow, body.article_ids, body.failure_code, state.clock
            )
        await audit.record(
            uow,
            actor_id=user.id,
            action=audit.AuditAction.PIPELINE_RETRIED,
            target_type="job" if body.job_ids is not None else "article",
            target_id=body.failure_code or "selection",
            after={**body.model_dump(mode="json"), "retried": n},
        )
    return RetryResult(retried=n, remaining=rest)
