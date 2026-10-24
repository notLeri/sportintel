"""Сводка аналитики (BE-T4.15): USpH, воронки, precision HIGH, правки черновиков (ADR-004: по origin)."""

import uuid
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from sportintel.modules.analytics.domain.metrics import (
    active_hours,
    draft_edit_ratio,
    median,
    useful_events,
)
from sportintel.platform.db import UnitOfWork

BRT = ZoneInfo("America/Sao_Paulo")
MAX_DRAFTS = 500


def _rate(n: int, hours: float) -> float | None:
    return round(n / hours, 3) if hours > 0 else None


async def build_summary(
    uow: UnitOfWork, frm: datetime, to: datetime, group_by: Literal["user", "day"], q: Any
) -> dict[str, Any]:
    """q — порт чтения представлений (infrastructure.queries)."""
    s = uow.session
    trans = await q.transitions(s, frm, to)
    ids = list({t["event_id"] for t in trans if t["event_id"]})
    current = await q.events_by_ids(s, ids)
    useful = useful_events(trans, current)
    acts = await q.activity(s, frm, to)
    by_user: dict[Any, list[datetime]] = defaultdict(list)
    by_day: dict[str, list[datetime]] = defaultdict(list)
    for a in acts:
        by_user[a["user_id"]].append(a["at"])
        by_day[a["at"].astimezone(BRT).date().isoformat()].append(a["at"])
    hours_user = {u: active_hours(ts) for u, ts in by_user.items()}
    total_hours = sum(hours_user.values())

    if group_by == "user":
        counts = Counter(actor for actor, _ in useful.values())
        keys = set(counts) | set(hours_user)
        rows = [
            {
                "key": str(k),
                "useful_stories": counts.get(k, 0),
                "active_hours": round(hours_user.get(k, 0.0), 3),
                "uspH": _rate(counts.get(k, 0), hours_user.get(k, 0.0)),
            }
            for k in keys
            if k is not None
        ]
    else:
        counts_d = Counter(at.astimezone(BRT).date().isoformat() for _, at in useful.values())
        hours_d: dict[str, float] = defaultdict(float)
        for u_ts in by_user.values():
            per_day: dict[str, list[datetime]] = defaultdict(list)
            for x in u_ts:
                per_day[x.astimezone(BRT).date().isoformat()].append(x)
            for d, ts in per_day.items():
                hours_d[d] += active_hours(ts)
        keys_d = sorted(set(counts_d) | set(hours_d))
        rows = [
            {
                "key": d,
                "useful_stories": counts_d.get(d, 0),
                "active_hours": round(hours_d.get(d, 0.0), 3),
                "uspH": _rate(counts_d.get(d, 0), hours_d.get(d, 0.0)),
            }
            for d in keys_d
        ]

    new = await q.events_new(s, frm, to)
    reached: dict[str, set[uuid.UUID]] = defaultdict(set)
    for t in trans:
        reached[t["to_status"]].add(t["event_id"])
    funnel = [{"status": "NEW", "count": len(new)}] + [
        {"status": st, "count": len(reached.get(st, set()))}
        for st in ("SELECTED", "DRAFT", "READY", "PUBLISHED", "REJECTED")
    ]

    first_seen = {e["id"]: e["first_seen_at"] for e in new} | {
        i: e["first_seen_at"] for i, e in current.items()
    }
    tts = [
        (at - first_seen[i]).total_seconds() / 60
        for i, (_, at) in useful.items()
        if i in first_seen
    ]
    reasons = Counter(t["reason"] for t in trans if t["to_status"] == "REJECTED" and t["reason"])

    highs = [e for e in new if e["relevance"] == "HIGH"]
    by_origin: dict[str, list[bool]] = defaultdict(list)
    for e in highs:
        by_origin[e["relevance_origin"]].append(e["id"] in useful)
    precision_high = (sum(e["id"] in useful for e in highs) / len(highs)) if highs else None

    ready_ids = list(reached.get("READY", set()) | reached.get("PUBLISHED", set()))[:MAX_DRAFTS]
    versions: dict[uuid.UUID, list[dict[str, Any]]] = defaultdict(list)
    for v in await q.drafts_for(s, ready_ids):
        versions[v["draft_id"]].append(v)
    ratios: dict[str, list[float]] = defaultdict(list)
    for vs in versions.values():
        first = next((v for v in vs if v["origin"] in {"template", "ai"}), None)
        if first and len(vs) > 1:
            ratios[first["origin"]].append(
                draft_edit_ratio(first["body_tg_html"], vs[-1]["body_tg_html"])
            )

    new_ids = [e["id"] for e in new]
    auto_events = {
        v["event_id"] for v in await q.drafts_for(s, new_ids) if v["auto"] and v["n"] == 1
    }
    feed_funnel = {
        "suggested": len(auto_events),
        "taken": len(auto_events & set(useful)),
        "published": len(auto_events & reached.get("PUBLISHED", set())),
    }

    leaders = Counter(
        (f["source_id"], f["source_name"]) for f in await q.first_sources(s, list(useful))
    )
    total_useful = len(useful)
    return {
        "totals": {
            "useful_stories": total_useful,
            "active_hours": round(total_hours, 3),
            "uspH": _rate(total_useful, total_hours),
            "events_new": len(new),
            "ai_cost_usd": 0.0,
            "ai_cost_per_useful": None,
        },  # ADR-004: AI бесплатен
        "rows": rows,
        "funnel": funnel,
        "time_to_select_p50_min": median(tts),
        "reject_reasons": [{"reason": r, "count": n} for r, n in reasons.most_common()],
        "precision_high": precision_high,
        "precision_high_by_origin": {k: sum(v) / len(v) for k, v in by_origin.items()},
        "draft_edit_ratio_p50": median([x for xs in ratios.values() for x in xs]),
        "draft_edit_ratio_p50_by_origin": {k: median(v) for k, v in ratios.items()},
        "feed_funnel": feed_funnel,
        "first_source_leaders": [
            {"source_id": sid, "name": name, "useful_first_count": n}
            for (sid, name), n in leaders.most_common(10)
        ],
    }
