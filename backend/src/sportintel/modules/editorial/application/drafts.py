"""Черновики Telegram (BE-T3.7, ADR-004: шаблон — синхронно, LM — фаза L)."""

import re
import uuid
from collections.abc import Callable
from typing import Any

from sportintel.modules.audit import public as audit
from sportintel.modules.editorial.domain.assemble import assemble, disclaimer_kinds
from sportintel.modules.editorial.domain.draft_output import clean
from sportintel.modules.editorial.domain.errors import (
    DisclaimerRemovalForbidden,
    EventStatusInvalid,
    GenerationInProgress,
)
from sportintel.modules.editorial.domain.limits import max_length, plain_length
from sportintel.modules.editorial.domain.template import PROMPT_VERSION, build
from sportintel.modules.editorial.domain.tg_html import sanitize_tg_html
from sportintel.modules.editorial.domain.values import DraftState, VersionOrigin
from sportintel.modules.events import public as events
from sportintel.platform import settings_store
from sportintel.platform.clock import Clock
from sportintel.platform.db import Database, UnitOfWork
from sportintel.platform.errors import ConcurrencyConflict, FieldError, NotFound, ValidationFailed
from sportintel.platform.ids import new_id

RepoFor = Callable[[UnitOfWork], Any]
DRAFTABLE = {"SELECTED", "DRAFT", "READY"}
EDITOR_ROLES = {"editor", "admin"}


async def _last_human(repo: Any, draft_id: uuid.UUID) -> uuid.UUID | None:
    for ver in await repo.versions(draft_id):
        if ver["origin"] == VersionOrigin.HUMAN and ver["author_id"]:
            return ver["author_id"]  # type: ignore[no-any-return]
    return None


async def add_template_version(
    db: Database,
    uow: UnitOfWork,
    repo: Any,
    draft: dict[str, Any],
    pack: Any,
    actor_id: uuid.UUID | None,
    clock: Clock,
) -> None:
    """Шаблонная версия n+1; нет источников → failed/generation_failed. Общая для API и ленты (BE-T3.15)."""
    drafts_cfg: Any = await settings_store.get(db, "drafts")
    langs: Any = await settings_store.get(db, "languages")
    now = clock.now()
    result = build(pack, drafts_cfg, langs.telegram_language)
    if result is None:
        await repo.update(
            draft["id"], now, state=DraftState.FAILED.value, failure_code="generation_failed"
        )
        await events.set_draft_status(
            uow, pack.event_id, DraftState.FAILED.value, await _last_human(repo, draft["id"])
        )
        return
    body = sanitize_tg_html(
        assemble(clean(result.output, drafts_cfg.max_hashtags), result.source_link)
    )
    n = draft["current_version"] + 1
    await repo.add_version(
        draft["id"],
        n,
        {
            "body_tg_html": body,
            "image_url": None,
            "disclaimer_kinds": [
                k.value
                for k in disclaimer_kinds(pack.reliability.level.value, pack.has_open_conflicts)
            ],
            "origin": VersionOrigin.TEMPLATE.value,
            "lang": result.language,  # текст статьи без перевода — её язык, не настройка
            "citations": [{"n": 1, "article_id": str(result.main_article_id)}],
            "grounding_report": {"skipped": "template"},
            "prompt_version": PROMPT_VERSION,
            "author_id": None,
        },
        now,
    )
    await repo.update(
        draft["id"], now, state=DraftState.READY.value, current_version=n, failure_code=None
    )
    await events.set_draft_status(
        uow, pack.event_id, DraftState.READY.value, await _last_human(repo, draft["id"])
    )
    if actor_id is not None:  # авто-черновик ленты статус не меняет (ADR-004)
        await events.system_transition(uow, pack.event_id, "DRAFT", clock)


async def add_brief_version(
    uow: UnitOfWork,
    repo: Any,
    draft: dict[str, Any],
    pack: Any,
    body_tg_html: str,
    brief: dict[str, Any],
    actor_id: uuid.UUID | None,
    clock: Clock,
) -> None:
    """Версия n+1 из AI-брифа на его языке (фаза 5): текст брифа становится постом для правки."""
    now, n = clock.now(), draft["current_version"] + 1
    await repo.add_version(
        draft["id"],
        n,
        {
            "body_tg_html": sanitize_tg_html(body_tg_html),
            "image_url": None,
            "disclaimer_kinds": [
                k.value
                for k in disclaimer_kinds(pack.reliability.level.value, pack.has_open_conflicts)
            ],
            "origin": VersionOrigin.AI.value,
            "lang": brief["lang"],
            "citations": [],
            "grounding_report": {"source_refs": brief["brief"]["source_refs"]},
            "prompt_version": brief["prompt_version"],
            "author_id": None,
        },
        now,
    )
    await repo.update(
        draft["id"], now, state=DraftState.READY.value, current_version=n, failure_code=None
    )
    await events.set_draft_status(
        uow, pack.event_id, DraftState.READY.value, await _last_human(repo, draft["id"])
    )
    if actor_id is not None and pack.status == "SELECTED":
        await events.system_transition(uow, pack.event_id, "DRAFT", clock)


BriefPost = tuple[dict[str, Any], str]  # (строка event_briefs, отрендеренный Telegram HTML)
AI_MODES = {
    "brief",
    "llm",
}  # готовый текст ИИ приходит из роутера (модель вызывается вне транзакции)


def _need_brief(mode: str, brief: BriefPost | None) -> BriefPost:
    if brief is None:
        raise ValidationFailed(
            details=[
                FieldError("lang", "brief_missing", "generate the AI brief in this language first")
            ]
        )
    return brief


async def request_generation(
    db: Database,
    uow: UnitOfWork,
    repo_for: RepoFor,
    event_id: uuid.UUID,
    actor_id: uuid.UUID,
    mode: str,
    clock: Clock,
    brief: BriefPost | None = None,
) -> tuple[uuid.UUID, bool]:
    """→ (draft_id, created). mode: template | empty | brief | llm (текст ИИ — в brief)."""
    repo = repo_for(uow)
    pack = await events.build_evidence_pack(uow, event_id, 12, clock)
    if pack.status not in DRAFTABLE:
        raise EventStatusInvalid(f"event is {pack.status}")
    draft = await repo.by_event(event_id, for_update=True)
    if mode in AI_MODES:
        _need_brief(mode, brief)
    if draft is not None:
        return draft[
            "id"
        ], False  # существующий (в т.ч. авто) — новая версия только через :regenerate
    draft_id, now = new_id(), clock.now()
    await repo.create(draft_id, event_id, DraftState.GENERATING.value, actor_id, now)
    draft = await repo.get(draft_id, for_update=True)
    assert draft is not None  # noqa: S101
    if mode == "empty":
        await repo.add_version(
            draft_id,
            1,
            {"body_tg_html": "", "origin": VersionOrigin.HUMAN.value, "author_id": actor_id},
            now,
        )
        await repo.update(draft_id, now, state=DraftState.READY.value, current_version=1)
        await events.set_draft_status(uow, event_id, DraftState.READY.value, actor_id)
        await events.system_transition(uow, event_id, "DRAFT", clock)
    elif mode in AI_MODES:
        row, body = _need_brief(mode, brief)
        await add_brief_version(uow, repo, draft, pack, body, row, actor_id, clock)
    else:
        await add_template_version(db, uow, repo, draft, pack, actor_id, clock)
    await audit.record(
        uow,
        actor_id=actor_id,
        action=audit.AuditAction.DRAFT_GENERATION_REQUESTED,
        target_type="draft",
        target_id=str(draft_id),
        after={"mode": mode},
        context_event_id=event_id,
    )
    return draft_id, True


async def regenerate(
    db: Database,
    uow: UnitOfWork,
    repo_for: RepoFor,
    draft_id: uuid.UUID,
    actor_id: uuid.UUID,
    clock: Clock,
    mode: str = "template",
    brief: BriefPost | None = None,
) -> None:
    repo = repo_for(uow)
    draft = await repo.get(draft_id, for_update=True)
    if draft is None:
        raise NotFound(f"draft {draft_id} not found")
    if draft["state"] == DraftState.GENERATING:
        raise GenerationInProgress()
    pack = await events.build_evidence_pack(uow, draft["event_id"], 12, clock)
    if pack.status not in DRAFTABLE:
        raise EventStatusInvalid(f"event is {pack.status}")
    if mode in AI_MODES:
        row, body = _need_brief(mode, brief)
        await add_brief_version(uow, repo, draft, pack, body, row, actor_id, clock)
    else:
        await add_template_version(db, uow, repo, draft, pack, actor_id, clock)
    await audit.record(
        uow,
        actor_id=actor_id,
        action=audit.AuditAction.DRAFT_GENERATION_REQUESTED,
        target_type="draft",
        target_id=str(draft_id),
        after={"mode": mode, "regenerate": True, "lang": brief[0]["lang"] if brief else None},
        context_event_id=draft["event_id"],
    )


async def add_translated_version(
    uow: UnitOfWork,
    repo_for: RepoFor,
    draft_id: uuid.UUID,
    from_n: int,
    body_tg_html: str,
    lang: str,
    actor_id: uuid.UUID,
    clock: Clock,
) -> None:
    """Версия n+1 — перевод версии from_n; картинка и дисклеймеры переносятся как есть."""
    repo = repo_for(uow)
    draft = await repo.get(draft_id, for_update=True)
    prev = await repo.version(draft_id, from_n)
    if draft is None or prev is None:
        raise NotFound(f"draft {draft_id} version {from_n} not found")
    now, n = clock.now(), draft["current_version"] + 1
    await repo.add_version(
        draft_id,
        n,
        {
            "body_tg_html": sanitize_tg_html(body_tg_html),
            "image_url": prev["image_url"],
            "disclaimer_kinds": list(prev["disclaimer_kinds"]),
            "disclaimer_removed": prev["disclaimer_removed"],
            "origin": VersionOrigin.AI.value,
            "lang": lang,
            "citations": prev["citations"],
            "grounding_report": {"translated_from": from_n},
            "prompt_version": "translate/v1",
            "author_id": None,
        },
        now,
    )
    await repo.update(draft_id, now, current_version=n)
    # Новая текущая версия — новый текст: утверждение «Готово» снимается (CONV §8.1),
    # иначе в канал ушёл бы перевод, которого редактор не утверждал.
    await events.system_transition(uow, draft["event_id"], "DRAFT", clock)
    await audit.record(
        uow,
        actor_id=actor_id,
        action=audit.AuditAction.DRAFT_GENERATION_REQUESTED,
        target_type="draft",
        target_id=str(draft_id),
        after={"mode": "translate", "from": from_n, "lang": lang},
        context_event_id=draft["event_id"],
    )


async def save_version(
    uow: UnitOfWork,
    repo_for: RepoFor,
    draft_id: uuid.UUID,
    data: dict[str, Any],
    actor_id: uuid.UUID,
    role: str,
    expected_version: int,
    clock: Clock,
    language: str = "en",
) -> None:
    repo = repo_for(uow)
    draft = await repo.get(draft_id, for_update=True)
    if draft is None:
        raise NotFound(f"draft {draft_id} not found")
    if draft["state"] == DraftState.GENERATING:
        raise GenerationInProgress()
    if draft["version"] != expected_version:
        raise ConcurrencyConflict(current=None)
    pack_status = (await events.build_evidence_pack(uow, draft["event_id"], 1, clock)).status
    if pack_status not in DRAFTABLE:
        raise EventStatusInvalid(f"event is {pack_status}")
    prev = (
        await repo.version(draft_id, draft["current_version"]) if draft["current_version"] else None
    )
    kinds = list(prev["disclaimer_kinds"]) if prev else []
    body = sanitize_tg_html(data["body_tg_html"])
    image = data.get("image_url")
    if not body and not image:
        raise ValidationFailed(details=[FieldError("body_tg_html", "empty", "body is empty")])
    removed = bool(data.get("disclaimer_removed"))
    if removed and kinds and role not in EDITOR_ROLES:
        raise DisclaimerRemovalForbidden()
    language = prev["lang"] if prev else language
    # Дисклеймер — пометка для редактора, в пост не входит: лимит считается по тексту поста.
    length, limit = plain_length(body), max_length(image is not None)
    if length > limit:
        raise ValidationFailed(
            details=[FieldError("body_tg_html", "too_long", f"{length} > {limit}")]
        )
    kept = {int(x) for x in re.findall(r"\[(\d{1,2})\]", body)}
    citations = [c for c in (prev["citations"] if prev else []) if c["n"] in kept]
    now, n = clock.now(), draft["current_version"] + 1
    await repo.add_version(
        draft_id,
        n,
        {
            "body_tg_html": body,
            "image_url": image,
            "disclaimer_kinds": kinds,
            "disclaimer_removed": removed,
            "origin": VersionOrigin.HUMAN.value,
            "lang": language,  # правка сохраняет язык версии
            "citations": citations,
            "grounding_report": None,
            "author_id": actor_id,
        },
        now,
    )
    await repo.update(
        draft_id,
        now,
        expected_version,
        current_version=n,
        state=DraftState.READY.value,
        failure_code=None,
    )
    await events.set_draft_status(uow, draft["event_id"], DraftState.READY.value, actor_id)
    if pack_status == "READY":  # повторное утверждение обязательно (CONV §8.1)
        await events.system_transition(uow, draft["event_id"], "DRAFT", clock)
    if removed and kinds:
        await audit.record(
            uow,
            actor_id=actor_id,
            action=audit.AuditAction.DRAFT_DISCLAIMER_REMOVED,
            target_type="draft",
            target_id=str(draft_id),
            context_event_id=draft["event_id"],
        )
    await audit.record(
        uow,
        actor_id=actor_id,
        action=audit.AuditAction.DRAFT_SAVED,
        target_type="draft",
        target_id=str(draft_id),
        after={"n": n, "length": length, "body": body[:2000]},
        context_event_id=draft["event_id"],
    )
