"""Ручная правка события и перегенерация summary (BE-T3.4)."""

import re
import uuid
from collections.abc import Callable
from typing import Any

from sportintel.modules.audit import public as audit
from sportintel.modules.events.domain.actor import Actor
from sportintel.modules.events.domain.event import UNSET
from sportintel.modules.events.domain.values import OverrideField, Role
from sportintel.modules.taxonomy import public as taxonomy
from sportintel.platform.clock import Clock
from sportintel.platform.db import UnitOfWork
from sportintel.platform.errors import ConcurrencyConflict, FieldError, NotFound, ValidationFailed

RepoFor = Callable[[UnitOfWork], Any]
FIELDS = ("title", "summary", "sport_id", "competition_id")


def _snap(e: Any) -> dict[str, Any]:
    return {
        "title": e.title,
        "summary": e.summary,
        "sport_id": e.sport_id,
        "competition_id": e.competition_id,
        "entities": sorted(str(i) for i, _ in e.entities),
    }


async def _validate(uow: UnitOfWork, patch: dict[str, Any]) -> None:
    if not patch:
        raise ValidationFailed(details=[FieldError("body", "empty", "nothing to change")])
    if patch.get("sport_id") is not None:
        active = {s.id for s in await taxonomy.list_sports(uow)}
        if patch["sport_id"] not in active:
            raise ValidationFailed(
                details=[FieldError("sport_id", "unknown", "unknown or inactive sport")]
            )
    wanted = {"competition_id": "competition", "team_ids": "team", "player_ids": "player"}
    by_field = {k: _ids(patch.get(k)) for k in wanted}
    ids = [i for v in by_field.values() for i in v]
    found = await taxonomy.get_entities(uow, ids) if ids else {}
    for k, kind in wanted.items():
        for i in by_field[k]:
            if i not in found or str(found[i].kind) != kind:
                raise ValidationFailed(
                    details=[FieldError(k, "wrong_kind", f"{i} is not a {kind}")]
                )


def _ids(v: Any) -> list[uuid.UUID]:
    return list(v) if isinstance(v, list) else ([v] if v else [])


async def edit_event(
    uow: UnitOfWork,
    repo_for: RepoFor,
    event_id: uuid.UUID,
    patch: dict[str, Any],
    actor_id: uuid.UUID,
    role: str,
    expected_version: int,
    clock: Clock,
) -> None:
    await _validate(uow, patch)
    repo = repo_for(uow)
    event = await repo.get(event_id, for_update=True)
    if event is None:
        raise NotFound(f"event {event_id} not found")
    if event.version != expected_version:
        raise ConcurrencyConflict(current=None)
    before = _snap(event)
    actor, now = Actor(actor_id, Role(role)), clock.now()
    changed = event.edit(actor, now, **{k: patch.get(k, UNSET) for k in FIELDS})
    if "team_ids" in patch or "player_ids" in patch:
        keep = [(i, r) for i, r in event.entities if r not in {"team", "player"}]
        teams = patch.get("team_ids", [i for i, r in event.entities if r == "team"])
        players = patch.get("player_ids", [i for i, r in event.entities if r == "player"])
        event.set_entities_manual(
            actor, [*keep, *((i, "team") for i in teams), *((i, "player") for i in players)], now
        )
        changed.add(OverrideField.ENTITIES)
        await repo.replace_entities(event_id, [(i, r, 1, True) for i, r in event.entities])
    if not changed:
        return  # ничего не изменилось — версия не растёт
    lines = [*event.search_doc.split("\n"), "", ""]
    event.search_doc = "\n".join([event.title, event.summary or "", *lines[2:]]).rstrip("\n")
    await repo.save(event, expected_version)
    if OverrideField.SUMMARY in changed:
        kept = {int(n) for n in re.findall(r"\[(\d+)\]", event.summary or "")}
        await repo.set_summary_citations(event_id, kept)
    b, a = audit.diff(before, _snap(event))
    await audit.record(
        uow,
        actor_id=actor_id,
        action=audit.AuditAction.EVENT_EDITED,
        target_type="event",
        target_id=str(event_id),
        before=b,
        after=a,
        context_event_id=event_id,
    )


async def request_summary_regeneration(
    uow: UnitOfWork,
    repo_for: RepoFor,
    event_id: uuid.UUID,
    actor_id: uuid.UUID,
    expected_version: int,
    clock: Clock,
) -> None:
    """Снять override summary. Режим rules: пересчёт делает refresh_event сразу после коммита (ADR-004)."""
    repo = repo_for(uow)
    event = await repo.get(event_id, for_update=True)
    if event is None:
        raise NotFound(f"event {event_id} not found")
    if event.version != expected_version:
        raise ConcurrencyConflict(current=None)
    event.clear_override(OverrideField.SUMMARY, clock.now())
    await repo.save(event, expected_version)
    await audit.record(
        uow,
        actor_id=actor_id,
        action=audit.AuditAction.EVENT_SUMMARY_REGENERATE_REQUESTED,
        target_type="event",
        target_id=str(event_id),
        context_event_id=event_id,
    )
