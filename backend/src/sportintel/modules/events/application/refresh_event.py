"""Задача events.refresh_event (BE-T2.17). Режим правил: экстрактивные title/summary синхронно (ADR-004)."""

import copy
import uuid
from collections.abc import Callable
from typing import Any

import structlog

from sportintel.modules.events.domain.computed import RefreshInputs, compute_state
from sportintel.modules.events.domain.stale import is_stale_by_hint
from sportintel.modules.events.domain.values import OverrideField, RelationKind
from sportintel.modules.ingestion import public as ingestion
from sportintel.modules.intelligence import public as intelligence
from sportintel.modules.sources import public as sources
from sportintel.modules.taxonomy import public as taxonomy
from sportintel.platform import settings_store
from sportintel.platform.clock import Clock
from sportintel.platform.db import Database, UnitOfWork

_log = structlog.get_logger("sportintel.events")
_NOT_STATE = {"links", "refresh_requested_at", "version"}


def _snapshot(e: Any) -> dict[str, Any]:
    return {k: copy.deepcopy(v) for k, v in vars(e).items() if k not in _NOT_STATE}


async def refresh_event(
    db: Database, event_id: uuid.UUID, clock: Clock, repo_for: Callable[[UnitOfWork], Any]
) -> bool:
    """True — состояние изменилось и сохранено."""
    routing: Any = await settings_store.get(db, "ai_routing")
    content: Any = await settings_store.get(db, "content")
    clustering: Any = await settings_store.get(db, "clustering")
    async with db.uow() as uow:
        repo = repo_for(uow)
        event = await repo.get(event_id, for_update=True)
        if event is None:
            return False
        ids = [lk.article_id for lk in event.links]
        arts = await ingestion.get_articles_meta(uow, ids)
        enr = await intelligence.get_enrichments(uow, ids)
        srcs = await sources.get_sources_meta(uow, {a.source_id for a in arts.values()})
        ent_ids = {row["entity_id"] for e in enr.values() for row in e.entities}
        ents = await taxonomy.get_entities(uow, ent_ids)
        # Старая новость (BE-T4.6): подсказки дат статей или похожее событие до окна кластеризации.
        primary = [lk.article_id for lk in event.links if not lk.is_duplicate]
        old = await repo.similar_old(
            event_id,
            event.centroid,
            event.title,
            event.occurred_at,
            clustering.stale_window_days,
            clustering.window_hours,
            clustering.stale_similarity,
        )
        stale = is_stale_by_hint(
            [enr[i].event_date_hint for i in primary if i in enr], event.occurred_at
        ) or bool(old)
        state = compute_state(
            RefreshInputs(
                links=event.links,
                articles=arts,
                enrichments=enr,
                sources=srcs,
                entities=ents,
                stale=stale,
                lead_max_chars=content.lead_max_chars,
                extractive=routing.event_summary
                == "rules",  # ponytail: llm-summary — фаза L (BE-T2.19)
            )
        )
        before = _snapshot(event)
        new_sport = state.sport_id != event.sport_id
        event.apply_computed(state, clock.now())
        if OverrideField.SPORT in event.manual_overrides and new_sport and state.sport_id:
            event.has_updates_since_edit = True
        changed = _snapshot(event) != before
        if changed:
            await repo.save(event, event.version)
        else:
            await repo.clear_refresh(event_id)
        if OverrideField.ENTITIES not in event.manual_overrides:
            await repo.replace_entities(
                event_id,
                [(i, r, state.entity_mentions.get(i, 1), False) for i, r in state.entities],
            )
        await repo.replace_relations(event_id, RelationKind.OLD_NEWS, old)
        await repo.replace_relations(
            event_id,
            RelationKind.RELATED,
            await repo.related_by_entities(event_id, event.occurred_at),
        )
    _log.info("events.refreshed", event_id=str(event_id), changed=changed)
    return changed
