"""Правила тихих отказов (BE-T4.13). Чистые функции: входы → срабатывания."""

import html
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

BRT = ZoneInfo("America/Sao_Paulo")
WATCHED_QUEUES = ("fetch", "ai")
TOP_TIERS = {"A", "OFFICIAL"}


@dataclass(frozen=True)
class SourceHealth:
    id: uuid.UUID
    name: str
    tier: str | None
    active: bool
    last_new_article_at: datetime | None
    consecutive_failures: int
    had_articles_7d: bool


@dataclass(frozen=True)
class HealthInputs:
    queue_ages_s: dict[str, int | None]
    ingest_lag_p95_s: int | None
    sources: list[SourceHealth] = field(default_factory=list)


# Сообщения администраторам — на языке интерфейса редакции (languages.ui_language)
TEXTS = {
    "ru": {
        "queue": "Очередь <b>{q}</b> стоит: самая старая задача ждёт {m} мин",
        "lag": "Задержка загрузки статей (p95): {m} мин",
        "silent": "Источник <b>{name}</b> без новых статей уже {h} ч",
        "failing": "Источник <b>{name}</b> не загрузился {n} раз подряд",
        "resolved": "Исправлено",
    },
    "en": {
        "queue": "Queue <b>{q}</b> is stuck: the oldest task has waited {m} min",
        "lag": "Article ingest delay (p95): {m} min",
        "silent": "Source <b>{name}</b> has had no new articles for {h} h",
        "failing": "Source <b>{name}</b> failed {n} times in a row",
        "resolved": "Resolved",
    },
}


def _t(lang: str) -> dict[str, str]:
    return TEXTS.get(lang, TEXTS["en"])


@dataclass(frozen=True)
class Firing:
    alert_key: str
    text: str


def _in_active_hours(now: datetime, cfg: Any) -> bool:
    h = now.astimezone(BRT).hour
    return bool(cfg.active_hours_start <= h < cfg.active_hours_end)


def evaluate(i: HealthInputs, now: datetime, cfg: Any, lang: str = "ru") -> list[Firing]:
    t = _t(lang)
    out: list[Firing] = []
    for q in WATCHED_QUEUES:
        age = i.queue_ages_s.get(q)
        if age is not None and age > cfg.queue_age_minutes * 60:
            out.append(
                Firing(
                    f"queue_stalled:{q}",
                    t["queue"].format(q=q, m=age // 60),
                )
            )
    if i.ingest_lag_p95_s is not None and i.ingest_lag_p95_s > cfg.ingest_lag_p95_minutes * 60:
        out.append(Firing("ingest_lag", t["lag"].format(m=i.ingest_lag_p95_s // 60)))
    active_hours = _in_active_hours(now, cfg)
    for s in i.sources:
        name = html.escape(s.name)
        if (
            active_hours
            and s.active
            and s.tier in TOP_TIERS
            and s.had_articles_7d
            and s.last_new_article_at
            and now - s.last_new_article_at > timedelta(hours=cfg.silent_source_hours)
        ):
            hours = int((now - s.last_new_article_at).total_seconds() // 3600)
            out.append(Firing(f"source_silent:{s.id}", t["silent"].format(name=name, h=hours)))
        if s.active and s.consecutive_failures >= cfg.fetch_fail_streak:
            out.append(
                Firing(
                    f"source_failing:{s.id}",
                    t["failing"].format(name=name, n=s.consecutive_failures),
                )
            )
    # ponytail: ai_budget/ai_errors/llm_offline — только при AI_PROVIDER≠none (фаза L, ADR-004).
    return out


def plan(
    firing: list[Firing],
    state: dict[str, dict[str, Any]],
    now: datetime,
    repeat_minutes: int,
    lang: str = "ru",
) -> list[tuple[str, str, bool]]:
    """→ [(alert_key, сообщение, firing после отправки)]: новые/повторные срабатывания и восстановления."""
    msgs: list[tuple[str, str, bool]] = []
    current = {f.alert_key: f for f in firing}
    for key, f in current.items():
        st = state.get(key)
        stale = (
            st is None
            or not st["firing"]
            or st["last_sent_at"] is None
            or st["last_sent_at"] < now - timedelta(minutes=repeat_minutes)
        )
        if stale:
            msgs.append((key, f"🔴 {f.text}", True))
    for key, st in state.items():
        if st["firing"] and key not in current:
            text = (st.get("details") or {}).get("text", key)
            msgs.append((key, f"✅ {_t(lang)['resolved']}: {text}", False))
    return msgs
