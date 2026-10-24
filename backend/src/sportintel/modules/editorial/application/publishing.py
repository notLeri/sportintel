"""Публикация в каналы по расписанию (фаза 6).

approval — только события «Готово» с постом на языке канала (человек утвердил текст);
auto — события выше порогов канала, текст из AI-брифа на языке канала, слухи не публикуются.
Статус проверки (дисклеймер, «подтверждено/слух») в пост не попадает — он для редактора.
"""

import uuid
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal, Protocol

import structlog

from sportintel.modules.editorial.application.brief import BriefSource, EventBrief, render_tg
from sportintel.modules.editorial.domain.channels import (
    RANK,
    Candidate,
    Channel,
    DigestItem,
    is_due,
    matches,
    render_digest,
)
from sportintel.modules.editorial.domain.limits import max_length, plain_length
from sportintel.modules.events import public as events
from sportintel.platform import settings_store
from sportintel.platform.clock import Clock
from sportintel.platform.db import Database, UnitOfWork
from sportintel.platform.ids import new_id

_log = structlog.get_logger("sportintel.editorial")
WINDOW = timedelta(days=3)
# Закреплённый пост, не ушедший вовремя (автопостинг был выключен), сам не уходит:
# в календаре он «пропущен» — перетащить заново или открепить.
MISSED_AFTER = timedelta(minutes=15)
ALL_OPEN = ["NEW", "REVIEWING", "SELECTED", "DRAFT", "READY"]
RepoFor = Callable[[UnitOfWork], Any]


class Publisher(Protocol):
    async def send(self, chat_id: str, html: str) -> int: ...


@dataclass(frozen=True)
class Post:
    event_id: uuid.UUID
    body: str  # готовый Telegram HTML
    headline: str
    url: str | None
    from_ready: bool  # approval: событие в READY → после отправки PUBLISHED


@dataclass
class RunReport:
    channels: int = 0
    sent: int = 0
    failed: int = 0
    skipped: int = 0


def channel_of(row: dict[str, Any]) -> Channel:
    return Channel(**{k: row[k] for k in Channel.__dataclass_fields__})


async def _post_for(
    uow: UnitOfWork,
    ch: Channel,
    cand: dict[str, Any],
    drafts_repo: Any,
    briefs_repo: Any,
    emoji_for: dict[str, str],
) -> tuple[Post | None, str]:
    """Пост на языке канала или причина пропуска."""
    eid, lang = cand["id"], ch.language
    headline = cand["title_i18n"].get(lang) or cand["title"]
    if ch.mode == "approval":
        # Только текущая версия — та, что редактор видел и утвердил статусом «Готово».
        # Более старая версия на языке канала — не утверждённый текст: её не отправляем.
        draft = await drafts_repo.by_event(eid)
        ver = (
            await drafts_repo.version(draft["id"], draft["current_version"])
            if draft and draft["current_version"]
            else None
        )
        if ver is None or ver["lang"] != lang:
            return None, "no_post_in_language"
        return Post(eid, ver["body_tg_html"], headline, None, True), ""
    row = await briefs_repo.get(eid, lang)
    if row is None:
        return None, "no_brief_yet"
    brief = EventBrief.model_validate(row["brief"])
    if brief.status == "rumor":
        return None, "rumor"
    srcs = [BriefSource(**s) for s in row["sources"]]
    body = render_tg(brief, srcs, lang, emoji_for.get(cand["sport_id"] or ""))
    url = next((s.url for s in srcs if s.n in brief.source_refs), None)
    return Post(eid, body, brief.headline, url, False), ""


async def plan_posts(
    db: Database,
    ch: Channel,
    now: datetime,
    channels_for: RepoFor,
    drafts_for: RepoFor,
    briefs_for: RepoFor,
    limit: int,
    pins: dict[uuid.UUID, datetime] | None = None,
) -> tuple[list[Post], list[tuple[Post, datetime]], Counter[str]]:
    """Посты очереди по cron (до limit), закреплённые на время (pins) и причины пропуска.
    Без отправки."""
    pins = pins or {}
    drafts_cfg: Any = await settings_store.get(db, "drafts")
    skipped: Counter[str] = Counter()
    posts: list[Post] = []
    pinned: list[tuple[Post, datetime]] = []
    async with db.uow() as uow:
        rows = await events.publish_candidates(
            uow,
            statuses=["READY"] if ch.mode == "approval" else ALL_OPEN,
            min_rank=RANK[ch.min_relevance],
            since=now - WINDOW,
            include=list(pins),
        )
        done = await channels_for(uow).published(ch.id, [r["id"] for r in rows])
        tiers = {sid: t for r in rows for sid, t in r["source_tiers"].items()}
        for r in rows:
            at = pins.get(r["id"])
            if r["id"] in done or (at is None and len(posts) >= limit):
                continue
            cand = Candidate(
                r["id"], r["status"], r["relevance"], r["reliability"], r["region"],
                r["sport_id"], list(r["source_ids"]),
            )  # fmt: skip
            if not matches(ch, cand, tiers):
                continue
            post, why = await _post_for(
                uow, ch, r, drafts_for(uow), briefs_for(uow),
                drafts_cfg.emojis,
            )  # fmt: skip
            if post is None:
                skipped[why] += 1
                continue
            if at is None:
                posts.append(post)
            else:
                pinned.append((post, at))
    return posts, pinned, skipped


def batches(ch: Channel, posts: list[Post]) -> list[tuple[str, list[Post]]]:
    """Сообщения одного запуска: пост на событие или один дайджест."""
    if ch.format == "digest" and posts:
        return [_digest(posts, ch.language)]
    return [(p.body, [p]) for p in posts]


async def run_channel(
    db: Database,
    ch: Channel,
    clock: Clock,
    publisher: Publisher,
    channels_for: RepoFor,
    drafts_for: RepoFor,
    briefs_for: RepoFor,
) -> RunReport:
    report = RunReport(channels=1)
    now = clock.now()
    async with db.uow() as uow:
        pins = await channels_for(uow).pins(ch.id)  # у закреплённых своё время
    posts, _, skipped = await plan_posts(
        db, ch, now, channels_for, drafts_for, briefs_for, ch.max_per_run, pins
    )
    report.skipped = sum(skipped.values())
    if skipped:
        _log.info("editorial.publish_skipped", channel=ch.name, why=dict(skipped))
    for body, members in batches(ch, posts):
        await _send(db, ch, body, members, publisher, clock, channels_for, report)
    async with db.uow() as uow:
        await channels_for(uow).mark_run(ch.id, now)
    _log.info("editorial.publish_run", channel=ch.name, **vars(report))
    return report


ANY_STATUS = [*ALL_OPEN, "PUBLISHED", "REJECTED"]


Blocker = Literal["language", "filters", "too_old"]


async def approval_blocker(
    uow: UnitOfWork, ch: Channel, event_id: uuid.UUID, post_lang: str, now: datetime
) -> Blocker | None:
    """Почему утверждённый («Готово») пост не уйдёт в канал с утверждением, или None.
    language — пост не на языке канала; filters — событие не проходит фильтры канала
    (важность, регион, спорт, источники); too_old — последняя статья старше окна свежести."""
    if post_lang != ch.language:
        return "language"
    rows = await events.publish_candidates(
        uow, statuses=ANY_STATUS, min_rank=0, since=now + WINDOW, include=[event_id]
    )
    if not rows:
        return "filters"
    r = rows[0]
    cand = Candidate(
        r["id"], "READY", r["relevance"], r["reliability"], r["region"], r["sport_id"],
        list(r["source_ids"]),
    )  # fmt: skip
    if not matches(ch, cand, r["source_tiers"]):
        return "filters"
    if r["last_article_at"] < now - WINDOW:
        return "too_old"
    return None


async def post_language(db: Database, channels_for: RepoFor) -> str:
    """Язык поста ИИ — язык каналов (включённых или нет); если каналов нет или языки разные —
    язык постов из настроек. Так пост сразу уходит в канал без перевода и повторного утверждения."""
    async with db.uow() as uow:
        langs = {c["language"] for c in await channels_for(uow).all()}
    if len(langs) == 1:
        return str(langs.pop())
    cfg: Any = await settings_store.get(db, "languages")
    return str(cfg.telegram_language)


def missed(at: datetime, now: datetime) -> bool:
    return at < now - MISSED_AFTER


async def run_pinned(
    db: Database,
    ch: Channel,
    clock: Clock,
    publisher: Publisher,
    channels_for: RepoFor,
    drafts_for: RepoFor,
    briefs_for: RepoFor,
) -> RunReport:
    """Закреплённые посты, чьё время наступило: каждый отдельным сообщением, вне cron."""
    report = RunReport(channels=1)
    now = clock.now()
    async with db.uow() as uow:
        pins = await channels_for(uow).pins(ch.id)
    due = {e: at for e, at in pins.items() if at <= now and not missed(at, now)}
    if not due:
        return report
    await send_pinned(db, ch, due, clock, publisher, channels_for, drafts_for, briefs_for, report)
    _log.info("editorial.publish_pinned", channel=ch.name, **vars(report))
    return report


async def send_pinned(
    db: Database,
    ch: Channel,
    due: dict[uuid.UUID, datetime],
    clock: Clock,
    publisher: Publisher,
    channels_for: RepoFor,
    drafts_for: RepoFor,
    briefs_for: RepoFor,
    report: RunReport,
) -> int:
    """Отправить посты событий due, каждый отдельным сообщением, и снять закрепление.
    Возвращает, сколько постов нашлось (событие могло перестать быть готовым)."""
    now = clock.now()
    _, pinned, _ = await plan_posts(db, ch, now, channels_for, drafts_for, briefs_for, 0, due)
    for post, _at in pinned:
        await _send(db, ch, post.body, [post], publisher, clock, channels_for, report)
    async with db.uow() as uow:  # не готовое к сроку событие возвращается в обычную очередь
        for event_id in due:
            await channels_for(uow).unpin(ch.id, event_id)
    return len(pinned)


def _digest(posts: list[Post], lang: str) -> tuple[str, list[Post]]:
    """Один пост со списком заголовков; что не влезло в лимит Telegram — уйдёт следующим запуском."""
    items: list[Post] = []
    for p in posts:
        body = render_digest([DigestItem(x.headline, x.url) for x in [*items, p]], lang)
        if plain_length(body) > max_length(False):
            break
        items.append(p)
    return render_digest([DigestItem(x.headline, x.url) for x in items], lang), items


async def _send(
    db: Database,
    ch: Channel,
    body: str,
    members: list[Post],
    publisher: Publisher,
    clock: Clock,
    channels_for: RepoFor,
    report: RunReport,
) -> None:
    """Одно сообщение в Telegram; запись в publications — на каждое событие сообщения."""
    message_id: int | None = None
    error: str | None = None
    try:
        message_id = await publisher.send(ch.tg_chat_id, body)
    except Exception as e:  # любая ошибка Telegram пишется в publications
        error = str(e)[:500]
    async with db.uow() as uow:
        for post in members:
            recorded = await channels_for(uow).record(
                {
                    "id": new_id(),
                    "channel_id": ch.id,
                    "event_id": post.event_id,
                    "status": "failed" if error else "sent",
                    "lang": ch.language,
                    "body_tg_html": body,
                    "tg_message_id": message_id,
                    "error": error,
                },
                clock.now(),
            )
            if recorded and not error and post.from_ready:
                await events.system_transition(uow, post.event_id, "PUBLISHED", clock)
            if recorded:
                report.sent += 0 if error else 1
    if error:
        report.failed += len(members)
        _log.warning("editorial.publish_failed", channel=ch.name, error=error)


async def run_due(
    db: Database,
    clock: Clock,
    publisher: Publisher,
    channels_for: RepoFor,
    drafts_for: RepoFor,
    briefs_for: RepoFor,
) -> RunReport:
    total = RunReport()
    async with db.uow() as uow:
        due = [channel_of(r) for r in await channels_for(uow).all(active_only=True)]
    repos = (channels_for, drafts_for, briefs_for)
    for ch in due:
        reports = [await run_pinned(db, ch, clock, publisher, *repos)]
        if is_due(ch, clock.now()):
            reports.append(await run_channel(db, ch, clock, publisher, *repos))
            total.channels += 1
        for r in reports:
            total.sent, total.failed, total.skipped = (
                total.sent + r.sent,
                total.failed + r.failed,
                total.skipped + r.skipped,
            )
    return total
