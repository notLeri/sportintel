"""Ручное создание события (BE-T3.6)."""

import uuid
from collections.abc import Callable
from typing import Any

from sportintel.modules.audit import public as audit
from sportintel.modules.events.application.edit_event import _validate
from sportintel.modules.events.domain.actor import Actor
from sportintel.modules.events.domain.event import Event
from sportintel.modules.events.domain.values import (
    AssessmentOrigin,
    OverrideField,
    Relevance,
    RelevanceAssessment,
    Reliability,
    ReliabilityAssessment,
    ReliabilityFactor,
    ReliabilityFactorItem,
    Role,
)
from sportintel.modules.ingestion import public as ingestion
from sportintel.platform.clock import Clock
from sportintel.platform.db import UnitOfWork
from sportintel.platform.errors import FieldError, ValidationFailed
from sportintel.platform.ids import new_id

RepoFor = Callable[[UnitOfWork], Any]
MANUAL_RATIONALE = "Criado manualmente"


async def create_manual_event(
    uow: UnitOfWork,
    repo_for: RepoFor,
    data: dict[str, Any],
    actor_id: uuid.UUID,
    role: str,
    clock: Clock,
) -> tuple[uuid.UUID, list[dict[str, Any]]]:
    """→ (event_id, skipped_urls). Любая ошибка откатывает и событие, и статьи (одна транзакция)."""
    await _validate(
        uow,
        {
            k: v
            for k, v in data.items()
            if k in {"sport_id", "competition_id", "team_ids", "player_ids"}
        }
        or {"title": data["title"]},
    )
    now, actor = clock.now(), Actor(actor_id, Role(role))
    e = Event.create_manual(
        new_id(),
        data["title"],
        data.get("summary"),
        data.get("sport_id"),
        data.get("competition_id"),
        actor,
        now,
    )
    # Relevance выставляет человек, иначе первый refresh без статей опустит событие до LOW (§22).
    e.relevance = RelevanceAssessment(
        Relevance.MEDIUM, MANUAL_RATIONALE, AssessmentOrigin.HUMAN, MANUAL_RATIONALE
    )
    e.reliability = ReliabilityAssessment(
        Reliability.UNKNOWN,
        (ReliabilityFactorItem(ReliabilityFactor.NO_ARTICLES),),
        AssessmentOrigin.RULE,
    )
    e.manual_overrides.add(OverrideField.RELEVANCE)
    entities = [
        *((i, "team") for i in data.get("team_ids") or []),
        *((i, "player") for i in data.get("player_ids") or []),
    ]
    if entities:
        e.set_entities_manual(actor, entities, now)
    e.search_doc = "\n".join([e.title, e.summary or ""])
    repo = repo_for(uow)
    await repo.add(e)
    if entities:
        await repo.replace_entities(e.id, [(i, r, 1, True) for i, r in entities])
    skipped: list[dict[str, Any]] = []
    errors: list[FieldError] = []
    for n, url in enumerate(data.get("urls") or []):
        try:
            article_id, _ = await ingestion.add_manual_url(uow, url, actor_id, now, e.id)
        except ValidationFailed:
            errors.append(FieldError(f"urls[{n}]", "article.invalid_url", "invalid article URL"))
            continue
        other = await repo.event_id_for_article(article_id)
        if other is not None and other != e.id:
            skipped.append(
                {"url": url, "event_id": other}
            )  # статья уже в другом событии — не переносим
    if errors:
        raise ValidationFailed(details=errors)
    await audit.record(
        uow,
        actor_id=actor_id,
        action=audit.AuditAction.EVENT_CREATED_MANUAL,
        target_type="event",
        target_id=str(e.id),
        after={k: v for k, v in data.items()},
        context_event_id=e.id,
    )
    return e.id, skipped
