"""Автоматические черновики для ленты (ADR-004, BE-T3.15)."""

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Literal

import structlog

from sportintel.modules.editorial.application import post_ai, publishing
from sportintel.modules.editorial.application.drafts import (
    RepoFor,
    add_brief_version,
    add_template_version,
)
from sportintel.modules.editorial.domain.values import DraftState, VersionOrigin
from sportintel.modules.events import public as events
from sportintel.platform import ai_usage, settings_store
from sportintel.platform.clock import Clock
from sportintel.platform.db import Database
from sportintel.platform.ids import new_id
from sportintel.platform.llm import LlmError, LlmProvider

_log = structlog.get_logger("sportintel.editorial")
RANK = {"HIGH": 3, "MEDIUM": 2, "LOW": 1, "IRRELEVANT": 0}
WINDOW = timedelta(days=3)
AI_BUDGET_S = 30  # запуск раз в минуту: новый пост не начинается позже 30-й секунды
BACKLOG = 2000  # ponytail: потолок подсчёта очереди; больше — уже не о чем советовать точнее


@dataclass(frozen=True)
class DraftSnapshot:
    created_by: Any
    state: str
    auto_basis_hash: str | None
    has_human_versions: bool


@dataclass
class AutodraftReport:
    created: int = 0
    rebuilt: int = 0
    skipped: int = 0
    failed: int = 0


def decide(draft: DraftSnapshot | None, cand: Any) -> Literal["create", "rebuild", "skip"]:
    if draft is None:
        return "create" if cand.has_articles else "skip"
    if (
        draft.created_by is None
        and not draft.has_human_versions
        and draft.state == DraftState.READY
        and draft.auto_basis_hash != cand.basis_hash
    ):
        return "rebuild"
    return "skip"


async def run(db: Database, repo_for: RepoFor, clock: Clock) -> AutodraftReport:
    cfg: Any = await settings_store.get(db, "drafts")
    report = AutodraftReport()
    async with db.uow() as uow:
        cands = await events.autodraft_candidates(
            uow, min_rank=RANK[cfg.auto_min_relevance], since=clock.now() - WINDOW
        )
    for cand in cands:
        try:
            async with db.uow() as uow:
                # «Взять» и пересборка сериализуются по событию (§12).
                await uow.advisory_xact_lock(f"draft:{cand.event_id}")
                if await events.event_status(uow, cand.event_id) not in {"NEW", "REVIEWING"}:
                    report.skipped += 1
                    continue
                repo = repo_for(uow)
                row = await repo.by_event(cand.event_id, for_update=True)
                snap = None
                if row is not None:
                    human = any(
                        v["origin"] == VersionOrigin.HUMAN for v in await repo.versions(row["id"])
                    )
                    snap = DraftSnapshot(
                        row["created_by"], row["state"], row["auto_basis_hash"], human
                    )
                action = decide(snap, cand)
                if action == "skip":
                    report.skipped += 1
                    continue
                now = clock.now()
                if row is None:
                    draft_id = new_id()
                    await repo.create(
                        draft_id, cand.event_id, DraftState.GENERATING.value, None, now
                    )
                    row = await repo.get(draft_id, for_update=True)
                pack = await events.build_evidence_pack(uow, cand.event_id, 12, clock)
                # шаблон — сразу; при auto_mode=llm его заменит ИИ-вариант (ai_first_version)
                await add_template_version(db, uow, repo, row, pack, None, clock)
                await repo.update(row["id"], now, auto_basis_hash=cand.basis_hash)
                if action == "create":
                    report.created += 1
                else:
                    report.rebuilt += 1
        except Exception:
            _log.exception("editorial.autodraft_failed", event_id=str(cand.event_id))
            report.failed += 1
    _log.info("editorial.autodraft_done", **vars(report))
    return report


def post_interval_s(typical_s: float) -> float:
    """Сколько в среднем занимает один пост в очереди: запуск раз в минуту, внутри — пока не
    вышел AI_BUDGET_S (медленная модель — один пост в минуту)."""
    if typical_s >= 60:
        return typical_s
    return 60 / (int(AI_BUDGET_S // max(typical_s, 1)) + 1)


async def ai_backlog(
    db: Database, repo_for: RepoFor, channels_for: RepoFor, clock: Clock
) -> list[Any]:
    """События, которым ИИ ещё должен написать пост (шаблон или пост не на языке канала),
    в порядке очереди: важные и свежие первыми. Пусто — ИИ-первый вариант выключен."""
    cfg: Any = await settings_store.get(db, "drafts")
    if cfg.auto_mode != "llm":
        return []
    lang = await publishing.post_language(db, channels_for)
    async with db.uow() as uow:
        cands = await events.autodraft_candidates(
            uow, min_rank=RANK[cfg.auto_min_relevance], since=clock.now() - WINDOW, limit=BACKLOG
        )
        need = await repo_for(uow).needing_ai([c.event_id for c in cands], lang)
    return [c.event_id for c in cands if c.event_id in need]


async def ai_first_version(
    db: Database, repo_for: RepoFor, channels_for: RepoFor, clock: Clock, llm: LlmProvider
) -> bool:
    """Один автоматический черновик → пост ИИ по формату редакции на языке канала: шаблон или
    пост не на языке канала (иначе «Лента» его не покажет).
    Первым — самое важное и свежее событие. Модель вызывается вне транзакции; если за это время
    черновик правили или событие взяли в работу, ответ модели выбрасывается. True — пост написан."""
    queue = await ai_backlog(db, repo_for, channels_for, clock)
    if not queue:
        return False
    event_id = queue[0]
    cfg: Any = await settings_store.get(db, "drafts")
    lang = await publishing.post_language(db, channels_for)
    async with db.uow() as uow:
        draft = await repo_for(uow).by_event(event_id)
        pack = await events.build_evidence_pack(uow, event_id, 1, clock)
    draft_id, n = draft["id"], draft["current_version"]
    try:
        async with ai_usage.track(db, "post", llm.model, event_id):
            body = await post_ai.ai_post(pack, lang, cfg, llm)
    except LlmError:
        _log.warning("editorial.ai_first_version_failed", event_id=str(event_id))
        return False
    if body is None:
        return False
    async with db.uow() as uow:
        await uow.advisory_xact_lock(f"draft:{event_id}")
        repo = repo_for(uow)
        draft = await repo.get(draft_id, for_update=True)
        status = await events.event_status(uow, event_id)
        if draft is None or draft["current_version"] != n or status not in {"NEW", "REVIEWING"}:
            return False
        row = {"lang": lang, "prompt_version": post_ai.PROMPT_VERSION, "brief": {"source_refs": []}}
        await add_brief_version(uow, repo, draft, pack, body, row, None, clock)
    _log.info("editorial.ai_first_version", event_id=str(event_id), lang=lang)
    return True
