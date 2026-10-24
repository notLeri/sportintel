"""Экран «Важность»: как правила оценят материал — до сохранения правил."""

from typing import Annotated, Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, ValidationError

from sportintel.modules.identity import public as identity
from sportintel.modules.intelligence.application.rule_enrich import find_entities
from sportintel.modules.intelligence.domain.rules import ArticleInput, explain
from sportintel.modules.taxonomy import public as taxonomy
from sportintel.platform import settings_store
from sportintel.platform.errors import FieldError, ValidationFailed

P = identity.Permission
router = APIRouter(
    prefix="/api/v1/relevance", tags=["relevance"], route_class=identity.PermissionedRoute
)


class RelevanceCheck(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    lead: str = Field(default="", max_length=5000)
    url: str = Field(default="https://example.com/", max_length=2000)
    # несохранённые правила с экрана; None — сохранённые
    rules: dict[str, Any] | None = None


class RelevancePart(BaseModel):
    kind: str
    name: str
    points: int
    where: str
    label: str


class RelevanceResult(BaseModel):
    is_sports: bool
    sport: str | None
    score: int
    level: str
    parts: list[RelevancePart]


@router.post(":check", openapi_extra=identity.route_permission(P.SETTINGS_MANAGE))
async def check(
    body: RelevanceCheck,
    request: Request,
    _: Annotated[identity.CurrentUser, identity.require(P.SETTINGS_MANAGE)],
) -> RelevanceResult:
    db = request.app.state.db
    rules: Any = await settings_store.get(db, "enrich_rules")
    if body.rules is not None:
        try:
            rules = settings_store.schema_for("enrich_rules").model_validate(
                {**rules.model_dump(), **body.rules}
            )
        except ValidationError as e:
            raise ValidationFailed(
                details=[FieldError("rules", "invalid", str(err["msg"])) for err in e.errors()]
            ) from None
    a = ArticleInput(body.url, body.title, body.lead or None, None, (), None, None)
    async with db.uow() as uow:
        found = await find_entities(uow, a)
        out = explain(a, rules, found)
        # турниры — на языке интерфейса (в текстах ищутся по названию из источников)
        comps = {p["name"] for p in out["parts"] if p["kind"] == "competition"}
        shown = await taxonomy.display_by_name(uow, comps, await settings_store.ui_language(uow))
    for p in out["parts"]:
        if p["kind"] == "competition":
            p["name"] = shown.get(p["name"], p["name"])
    return RelevanceResult(**out)
