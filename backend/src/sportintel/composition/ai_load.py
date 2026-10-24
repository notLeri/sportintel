"""Нагрузка ИИ: что модель делает сейчас и сколько ждать (прогресс), справляется ли она
с потоком событий и что настроить, если нет (аналитика).

Склейка editorial (очереди постов и переводов), platform.ai_usage (замеры) и analytics.* (поток
событий по источникам). Советы — чистая функция advise()."""

import uuid
from datetime import date, datetime, time, timedelta
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel
from sqlalchemy import text

from sportintel.modules.editorial import public as editorial
from sportintel.modules.events import public as events
from sportintel.modules.identity import public as identity
from sportintel.platform import ai_usage, jobs, settings_store
from sportintel.platform.errors import FieldError, ValidationFailed

P = identity.Permission
router = APIRouter(tags=["ai"], route_class=identity.PermissionedRoute)
BRT = ZoneInfo("America/Sao_Paulo")
DAY_S = 86_400
LEVELS = ("HIGH", "MEDIUM", "LOW")
TIGHT, OVERLOADED = 0.5, 0.85  # доля суток, занятая ИИ: дальше очередь копится
FAILING = 0.5  # доля упавших среди последних вызовов: ИИ недоступен или модели нет
NEXT = 3
NOISY_MIN = 10  # источник «шумит»: столько важных событий за период, и ни одно не взято
TRANSLATE_CALLS = 3.0  # вызовов модели на событие, пока нет замеров (заголовок + статьи)


class AiQueueItem(BaseModel):
    event_id: uuid.UUID
    title: str


class AiRunning(BaseModel):
    kind: str
    event_id: uuid.UUID | None
    title: str | None
    elapsed_s: float
    typical_s: float


class AiQueue(BaseModel):
    kind: Literal["post", "translate", "brief"]
    pending: int
    eta_s: int
    done_24h: int
    next: list[AiQueueItem]


class AiProgress(BaseModel):
    running: list[AiRunning]
    queues: list[AiQueue]
    typical_s: dict[str, float]


async def _titles(uow: Any, ids: list[uuid.UUID], lang: str) -> dict[uuid.UUID, str]:
    return {
        e.id: e.title_i18n.get(lang) or e.title for e in await events.feed_events_by_ids(uow, ids)
    }


def _calls_per_event(st: dict[str, Any] | None) -> float:
    return st["calls"] / st["events"] if st and st["events"] else TRANSLATE_CALLS


@router.get("/api/v1/ai/progress", openapi_extra=identity.route_permission(P.EVENTS_READ))
async def progress(
    request: Request, _: Annotated[identity.CurrentUser, identity.require(P.EVENTS_READ)]
) -> AiProgress:
    """Что ИИ пишет сейчас (сколько прошло из обычного) и сколько ждут очереди."""
    state = request.app.state
    backlog = await editorial.ai_backlog(state.db, state.clock)
    langs: Any = await settings_store.get(state.db, "languages")
    async with state.db.uow() as uow:
        typical = await ai_usage.typical_s(uow.session)
        running = await ai_usage.running(uow.session)
        done = await ai_usage.done_since(uow.session, 24)
        now = state.clock.now()
        day = await ai_usage.stats(uow.session, now - timedelta(days=1), now + timedelta(minutes=1))
        briefs = (await jobs.pending_by_task(uow.session, ["editorial.build_brief"])).get(
            "editorial.build_brief", 0
        )
        busy = {r["event_id"] for r in running}
        nxt = {k: [i for i in v if i not in busy][:NEXT] for k, v in backlog.items()}
        ids = [r["event_id"] for r in running if r["event_id"]] + nxt["post"] + nxt["translate"]
        titles = await _titles(uow, list(dict.fromkeys(ids)), langs.ui_language)
    per = {
        "post": editorial.post_interval_s(typical["post"]),
        "translate": typical["translate"] * _calls_per_event(day.get("translate")),
        "brief": typical["brief"],
    }
    pending: dict[Literal["post", "translate", "brief"], int] = {
        "post": len(backlog["post"]),
        "translate": len(backlog["translate"]),
        "brief": briefs,
    }
    queues = [
        AiQueue(
            kind=k,
            pending=n,
            eta_s=round(n * per[k]),
            done_24h=done.get(k, 0),
            next=[AiQueueItem(event_id=i, title=titles[i]) for i in nxt.get(k, []) if i in titles],
        )
        for k, n in pending.items()
    ]
    return AiProgress(
        running=[
            AiRunning(
                kind=r["kind"],
                event_id=r["event_id"],
                title=titles.get(r["event_id"]) if r["event_id"] else None,
                elapsed_s=round(float(r["elapsed_s"]), 1),
                typical_s=typical.get(r["kind"], ai_usage.DEFAULT_S["post"]),
            )
            for r in running
        ],
        queues=queues,
        typical_s=typical,
    )


# --- Аналитика: справляется ли ИИ и что настроить ---------------------------------------------


def _from(level: str) -> list[str]:
    return list(LEVELS[: LEVELS.index(level) + 1])


def need_s_per_day(
    per_day: dict[str, float],
    typical: dict[str, float],
    calls_per_event: float,
    cfg: dict[str, Any],
) -> dict[str, float]:
    """Секунд модели в сутки по видам работы при этих настройках и этом потоке событий.
    post_queue — сколько занимает очередь постов с учётом запуска раз в минуту."""
    posts = (
        sum(per_day.get(lv, 0) for lv in _from(cfg["post_min"])) if cfg["post_mode"] == "llm" else 0
    )
    tr = sum(per_day.get(lv, 0) for lv in _from(cfg["translate_min"]))
    # ниже порога (и «не по теме») переводится только заголовок — один вызов
    titles = sum(n for lv, n in per_day.items() if lv not in _from(cfg["translate_min"]))
    br = sum(per_day.get(lv, 0) for lv in _from(cfg["brief_min"])) * len(cfg["brief_langs"])
    return {
        "post": posts * typical["post"],
        "post_queue": posts * editorial.post_interval_s(typical["post"]),
        "translate": (tr * calls_per_event + titles) * typical["translate"],
        "brief": br * typical["brief"],
    }


def load_share(need: dict[str, float]) -> float:
    """Доля суток, которую ИИ занят: модель одна на всё, а очередь постов — ещё и по минутам."""
    model = need["post"] + need["translate"] + need["brief"]
    return max(model, need["post_queue"]) / DAY_S


def verdict(
    share: float, backlog_eta_s: float, failed_share: float | None = None
) -> Literal["ok", "tight", "overloaded", "failing"]:
    # упавший вызов длится миллисекунды: занятость ≈ 0, и без этой проверки вердикт — «ok»
    if failed_share is not None and failed_share >= FAILING:
        return "failing"
    if share >= OVERLOADED or backlog_eta_s > 12 * 3600:
        return "overloaded"
    if share >= TIGHT or backlog_eta_s > 3 * 3600:
        return "tight"
    return "ok"


def advise(
    per_day: dict[str, float],
    typical: dict[str, float],
    calls_per_event: float,
    cfg: dict[str, Any],
    noisy: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Что настроить, чтобы ИИ успевал: каждое изменение — с нагрузкой после него.
    apply — {key, field, value} для одной кнопки «Применить»; link — куда идти руками."""

    def after(**change: Any) -> float:
        return round(load_share(need_s_per_day(per_day, typical, calls_per_event, cfg | change)), 3)

    out: list[dict[str, Any]] = []

    def add(id_: str, key: str | None, field: str | None, value: Any, share: float | None) -> None:
        apply = {"key": key, "field": field, "value": value} if key else None
        out.append({"id": id_, "apply": apply, "link": None, "share_after": share, "params": {}})

    if cfg["post_mode"] == "llm" and cfg["post_min"] != "HIGH":
        add("posts_high", "drafts", "auto_min_relevance", "HIGH", after(post_min="HIGH"))
    if cfg["translate_min"] != "HIGH":
        add(
            "translate_high",
            "languages",
            "translate_min_relevance",
            "HIGH",
            after(translate_min="HIGH"),
        )
    if cfg["brief_langs"]:
        add("briefs_off", "briefs", "auto_languages", [], after(brief_langs=[]))
    if cfg["post_mode"] == "llm":
        add("posts_by_button", "drafts", "auto_mode", "template", after(post_mode="template"))
    if typical["post"] > 30 or typical["translate"] > 15:
        out.append(
            {
                "id": "smaller_model",
                "apply": None,
                "link": "/admin/settings",
                "share_after": None,
                "params": {"model": cfg["llm_model"], "post_s": round(typical["post"])},
            }
        )
    for s in noisy:
        out.append(
            {
                "id": "noisy_source",
                "apply": None,
                "link": f"/admin/sources/{s['source_id']}",
                "share_after": None,
                "params": {
                    "name": s["source_name"],
                    "events": s["events"],
                    "source_id": str(s["source_id"]),
                },
            }
        )
    # сначала то, что сильнее разгружает; ручные советы — в конце
    return sorted(out, key=lambda a: a["share_after"] if a["share_after"] is not None else 9)


class AiKindStat(BaseModel):
    kind: str
    calls: int
    failed: int
    p50_s: float | None
    busy_s: float


class AiAdvice(BaseModel):
    id: str
    apply: dict[str, Any] | None
    link: str | None
    share_after: float | None
    params: dict[str, Any]


class AiLoad(BaseModel):
    verdict: Literal["off", "ok", "tight", "overloaded", "failing"]
    share: float  # доля суток, нужная ИИ при текущих настройках и потоке
    busy_share: float  # доля периода, которую модель на деле работала
    events_per_day: dict[str, float]
    sources: int  # источников, давших события HIGH/MEDIUM за период
    need_s_per_day: dict[str, float]
    kinds: list[AiKindStat]
    backlog: dict[str, int]
    backlog_eta_s: int
    headroom_events_per_day: int  # сколько ещё важных событий в сутки ИИ потянет до «на пределе»
    settings: dict[str, Any]
    advice: list[AiAdvice]


def _day_start(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=BRT)


async def _rows(s: Any, sql: str, **p: Any) -> list[dict[str, Any]]:
    return [dict(r._mapping) for r in await s.execute(text(sql), p)]


@router.get("/api/v1/analytics/ai-load", openapi_extra=identity.route_permission(P.ANALYTICS_READ))
async def ai_load(
    request: Request,
    _: Annotated[identity.CurrentUser, identity.require(P.ANALYTICS_READ)],
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
) -> AiLoad:
    state = request.app.state
    now = state.clock.now()
    end = to or now.astimezone(BRT).date()
    start = from_ or end - timedelta(days=6)
    if start > end:
        raise ValidationFailed(details=[FieldError("from", "invalid", "from ≤ to")])
    frm, till = _day_start(start), min(_day_start(end + timedelta(days=1)), now)
    days = max((till - frm).total_seconds() / DAY_S, 1 / 24)
    drafts: Any = await settings_store.get(state.db, "drafts")
    langs: Any = await settings_store.get(state.db, "languages")
    br: Any = await settings_store.get(state.db, "briefs")
    routing: Any = await settings_store.get(state.db, "ai_routing")
    cfg = {
        "post_min": drafts.auto_min_relevance,
        "post_mode": drafts.auto_mode,
        "translate_min": langs.translate_min_relevance,
        "brief_min": br.auto_min_relevance,
        "brief_langs": list(br.auto_languages),
        "llm_model": routing.llm_model,
        "translation_model": routing.translation_model,
    }
    backlog = await editorial.ai_backlog(state.db, state.clock)
    async with state.db.uow() as uow:
        s = uow.session
        stats = await ai_usage.stats(s, frm, till)
        typical = await ai_usage.typical_s(s)
        failed_share = await ai_usage.recent_failed_share(s)
        counts = await _rows(
            s,
            "SELECT relevance, count(*) AS n FROM analytics.v_events"
            " WHERE first_seen_at >= :f AND first_seen_at < :t GROUP BY relevance",
            f=frm,
            t=till,
        )
        by_source = await _rows(
            s,
            "SELECT f.source_id, f.source_name, count(*) AS events, count(*) FILTER"
            " (WHERE e.status IN ('SELECTED', 'DRAFT', 'READY', 'PUBLISHED')) AS used"
            " FROM analytics.v_first_sources f JOIN analytics.v_events e ON e.id = f.event_id"
            " WHERE e.first_seen_at >= :f AND e.first_seen_at < :t"
            " AND e.relevance IN ('HIGH', 'MEDIUM') GROUP BY 1, 2 ORDER BY 3 DESC",
            f=frm,
            t=till,
        )
    per_day = {r["relevance"]: round(r["n"] / days, 1) for r in counts if r["relevance"]}
    cpe = _calls_per_event(stats.get("translate"))
    need = need_s_per_day(per_day, typical, cpe, cfg)
    share = load_share(need)
    eta = (
        len(backlog["post"]) * editorial.post_interval_s(typical["post"])
        + len(backlog["translate"]) * cpe * typical["translate"]
    )
    # шумные источники — только если редакция вообще что-то берёт, иначе «шумят» все
    used_any = sum(r["used"] for r in by_source) >= 5
    noisy = [r for r in by_source if used_any and r["events"] >= NOISY_MIN and not r["used"]][:3]
    v: Literal["off", "ok", "tight", "overloaded", "failing"] = (
        "off" if state.settings.ai_provider == "none" else verdict(share, eta, failed_share)
    )
    # одно важное событие (MEDIUM+) стоит поста и перевода
    per_event = (typical["post"] if cfg["post_mode"] == "llm" else 0) + cpe * typical["translate"]
    headroom = max(0, int((TIGHT - share) * DAY_S / per_event)) if per_event else 0
    return AiLoad(
        verdict=v,
        share=round(share, 3),
        busy_share=round(sum(x["busy_s"] for x in stats.values()) / (days * DAY_S), 3),
        events_per_day=per_day,
        sources=len(by_source),
        need_s_per_day={k: round(x) for k, x in need.items()},
        kinds=[
            AiKindStat(
                kind=k, calls=x["calls"], failed=x["failed"], p50_s=x["p50_s"], busy_s=x["busy_s"]
            )
            for k, x in stats.items()
        ],
        backlog={k: len(x) for k, x in backlog.items()},
        backlog_eta_s=round(eta),
        headroom_events_per_day=headroom,
        settings=cfg,
        advice=[AiAdvice(**a) for a in advise(per_day, typical, cpe, cfg, noisy)]
        if v in {"tight", "overloaded"}
        else [],
    )
