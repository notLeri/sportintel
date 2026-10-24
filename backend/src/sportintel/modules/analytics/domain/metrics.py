"""Метрики аналитики (BE-T4.15). Чистые функции."""

import difflib
import re
import uuid
from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import Any

GAP = timedelta(minutes=15)
MIN_CREDIT = timedelta(minutes=5)
USEFUL_STATUSES = {"SELECTED", "DRAFT", "READY", "PUBLISHED"}
NOT_USEFUL_REJECTIONS = {"DUPLICATE", "INCORRECT"}


def active_hours(
    ts: list[datetime], gap: timedelta = GAP, min_credit: timedelta = MIN_CREDIT
) -> float:
    """Сессии рвутся на паузах > gap; длительность сессии = last − first + min_credit."""
    if not ts:
        return 0.0
    total, start, prev = timedelta(0), ts[0], ts[0]
    for t in ts[1:]:
        if t - prev > gap:
            total += prev - start + min_credit
            start = t
        prev = t
    total += prev - start + min_credit
    return total.total_seconds() / 3600


def useful_events(
    transitions: Iterable[dict[str, Any]], current: dict[uuid.UUID, dict[str, Any]]
) -> dict[uuid.UUID, tuple[Any, datetime]]:
    """Первый переход события в SELECTED/DRAFT/READY/PUBLISHED; исключаются REJECTED как DUPLICATE/INCORRECT."""
    out: dict[uuid.UUID, tuple[Any, datetime]] = {}
    for t in sorted(transitions, key=lambda x: x["at"]):
        e = current.get(t["event_id"])
        if t["to_status"] not in USEFUL_STATUSES or t["event_id"] in out or e is None:
            continue
        if e["status"] == "REJECTED" and e["rejection_reason"] in NOT_USEFUL_REJECTIONS:
            continue
        out[t["event_id"]] = (t["actor_id"], t["at"])
    return out


_TAG = re.compile(r"<[^>]+>")


def draft_edit_ratio(first_body: str, final_body: str) -> float:
    """Доля правки: 1 − сходство plain-текстов (difflib)."""
    a, b = _TAG.sub("", first_body), _TAG.sub("", final_body)
    return 1 - difflib.SequenceMatcher(None, a, b).ratio()


def median(xs: list[float]) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    m = len(s) // 2
    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2
