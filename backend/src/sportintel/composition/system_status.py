"""Системный статус для UI (BE-T4.14, ADR-004): режим AI, недоступные источники, задержка конвейера."""

import time
from typing import Any

from sqlalchemy import text

from sportintel.platform import settings_store
from sportintel.platform.config import Settings
from sportintel.platform.db import Database

CACHE_S = 60
_cache: list[tuple[float, dict[str, Any]]] = []
STEPS = (
    "enrich_article",
    "cluster_adjudicate",
    "event_summary",
    "telegram_draft",
    "conflict_check",
)


def ai_mode(routing: Any) -> str:
    modes = {"llm" if getattr(routing, s) == "llm" else "rules" for s in STEPS}
    return modes.pop() if len(modes) == 1 else "mixed"


async def compute(db: Database, settings: Settings) -> dict[str, Any]:
    if _cache and _cache[0][0] > time.monotonic():
        return _cache[0][1]
    routing: Any = await settings_store.get(db, "ai_routing")
    configured = settings.ai_provider == "ollama"
    async with db.uow() as uow:
        down = (
            await uow.session.execute(
                text("SELECT count(*) FROM sources.sources WHERE active AND health = 'down'")
            )
        ).scalar()
        delayed = (
            await uow.session.execute(
                text(
                    "SELECT exists(SELECT 1 FROM platform.alert_state WHERE firing AND (alert_key LIKE 'queue_stalled:%' OR alert_key = 'ingest_lag'))"
                )
            )
        ).scalar()
    status = {
        "ai": {
            "mode": ai_mode(routing),
            # ponytail: доступность LM проверит клиент Ollama (фаза L); пока «настроена» = «доступна».
            "llm": {
                "configured": configured,
                "available": configured,
                "model": routing.llm_model if configured else None,
            },
        },
        "sources_down": int(down or 0),
        "pipeline_delayed": bool(delayed),
    }
    _cache[:] = [(time.monotonic() + CACHE_S, status)]
    return status


def clear_cache() -> None:
    _cache.clear()
