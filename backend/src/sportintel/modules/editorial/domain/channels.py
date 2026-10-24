"""Каналы Telegram: какие события публиковать и когда (фаза 6). Чистые функции, без I/O."""

import html
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from croniter import croniter

RANK = {"HIGH": 3, "MEDIUM": 2, "LOW": 1, "IRRELEVANT": 0, "UNKNOWN": 0}
TIER_RANK = {"OFFICIAL": 4, "A": 3, "B": 2, "C": 1, "UNTRUSTED": 0}
DIGEST_TITLE = {"ru": "Главное", "en": "Top stories", "pt-BR": "Destaques"}


@dataclass(frozen=True)
class Channel:
    id: uuid.UUID
    name: str
    tg_chat_id: str
    language: str
    mode: str  # approval — только утверждённые (READY); auto — по порогам без участия человека
    cron: str
    format: str  # single — пост на событие; digest — один пост со списком
    max_per_run: int
    min_relevance: str = "HIGH"
    min_trust: str = "MEDIUM"
    min_tier: str | None = None
    regions: list[str] = field(default_factory=list)
    sports: list[str] = field(default_factory=list)
    source_allow: list[uuid.UUID] = field(default_factory=list)
    source_deny: list[uuid.UUID] = field(default_factory=list)
    last_run_at: datetime | None = None


@dataclass(frozen=True)
class Candidate:
    event_id: uuid.UUID
    status: str
    relevance: str
    reliability: str
    region: str | None
    sport_id: str | None
    source_ids: list[uuid.UUID]


def is_due(ch: Channel, now: datetime) -> bool:
    """Наступил ли слот расписания после прошлого запуска. Новый канал запускается сразу."""
    if ch.last_run_at is None:
        return True
    nxt: datetime = croniter(ch.cron, ch.last_run_at).get_next(datetime)
    return nxt <= now


def next_runs(ch: Channel, now: datetime, n: int) -> list[datetime]:
    """Ближайшие n запусков (UTC). Наступивший слот — «сейчас»: worker проверяет каналы раз в минуту."""
    first = now if is_due(ch, now) else croniter(ch.cron, ch.last_run_at).get_next(datetime)
    it = croniter(ch.cron, first)
    return [first, *(it.get_next(datetime) for _ in range(n - 1))]


def runs_until(ch: Channel, now: datetime, until: datetime, cap: int) -> list[datetime]:
    """Запуски от ближайшего до until (не больше cap) — для календаря на несколько недель."""
    runs = next_runs(ch, now, 1)
    it = croniter(ch.cron, runs[0])
    while len(runs) < cap:
        nxt: datetime = it.get_next(datetime)
        if nxt > until:
            break
        runs.append(nxt)
    return runs


def valid_cron(expr: str) -> bool:
    return bool(croniter.is_valid(expr))


def matches(ch: Channel, c: Candidate, tiers: dict[uuid.UUID, str | None]) -> bool:
    """Фильтры канала. tiers — уровень доверия источников события."""
    if ch.mode == "approval" and c.status != "READY":
        return False
    if ch.mode == "auto" and c.status == "REJECTED":
        return False
    if RANK.get(c.relevance, 0) < RANK[ch.min_relevance]:
        return False
    if ch.mode == "auto" and RANK.get(c.reliability, 0) < RANK[ch.min_trust]:
        return False
    if ch.regions and c.region not in ch.regions:
        return False
    if ch.sports and c.sport_id not in ch.sports:
        return False
    if ch.source_allow and not set(c.source_ids) & set(ch.source_allow):
        return False
    if ch.source_deny and set(c.source_ids) & set(ch.source_deny):
        return False
    if ch.min_tier:
        best = max((TIER_RANK.get(tiers.get(s) or "", 0) for s in c.source_ids), default=0)
        if best < TIER_RANK[ch.min_tier]:
            return False
    return True


@dataclass(frozen=True)
class DigestItem:
    headline: str
    url: str | None


def render_digest(items: list[DigestItem], lang: str) -> str:
    title = DIGEST_TITLE.get(lang, DIGEST_TITLE["en"])
    lines = [f"<b>{html.escape(title, quote=False)}</b>", ""]
    for it in items:
        text = html.escape(it.headline, quote=False)
        lines.append(f'• <a href="{html.escape(it.url)}">{text}</a>' if it.url else f"• {text}")
    return "\n".join(lines)
