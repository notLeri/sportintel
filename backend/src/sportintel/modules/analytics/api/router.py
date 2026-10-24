"""`/api/v1/analytics` (BE-T4.15)."""

import uuid
from datetime import date, datetime, time, timedelta
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel

from sportintel.modules.analytics.application.summary import build_summary
from sportintel.modules.analytics.infrastructure import queries
from sportintel.modules.identity import public as identity
from sportintel.platform.errors import FieldError, ValidationFailed

P = identity.Permission
router = APIRouter(
    prefix="/api/v1/analytics", tags=["analytics"], route_class=identity.PermissionedRoute
)
BRT = ZoneInfo("America/Sao_Paulo")
MAX_DAYS = 92


class Heartbeat(BaseModel):
    event_id: uuid.UUID | None = None


def _day_start(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=BRT)


@router.get("/summary", openapi_extra=identity.route_permission(P.ANALYTICS_READ))
async def summary(
    request: Request,
    _: Annotated[identity.CurrentUser, identity.require(P.ANALYTICS_READ)],
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
    group_by: Literal["user", "day"] = "user",
) -> dict[str, Any]:
    today = request.app.state.clock.now().astimezone(BRT).date()
    end, start = (to or today), (from_ or (to or today) - timedelta(days=6))
    if start > end or (end - start).days >= MAX_DAYS:
        raise ValidationFailed(
            details=[FieldError("from", "invalid", f"from ≤ to and at most {MAX_DAYS} days")]
        )
    async with request.app.state.db.uow() as uow:
        out = await build_summary(
            uow, _day_start(start), _day_start(end + timedelta(days=1)), group_by, queries
        )
        if group_by == "user":
            names = await identity.user_names(uow, [uuid.UUID(r["key"]) for r in out["rows"]])
            for r in out["rows"]:
                r["label"] = names.get(uuid.UUID(r["key"]), "—")
        else:
            for r in out["rows"]:
                r["label"] = r["key"]
    out["rows"].sort(key=lambda r: (-r["useful_stories"], r["label"]))
    return out


@router.post("/heartbeat", status_code=204, openapi_extra=identity.route_permission(P.EVENTS_READ))
async def heartbeat(
    body: Heartbeat,
    request: Request,
    user: Annotated[identity.CurrentUser, identity.require(P.EVENTS_READ)],
) -> Response:
    async with request.app.state.db.uow() as uow:
        await queries.add_heartbeat(
            uow.session, user.id, body.event_id, request.app.state.clock.now()
        )
    return Response(status_code=204)
