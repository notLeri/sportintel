"""Чтение представлений analytics.* (данные других модулей — только через view, CONV §7.2)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def _all(s: AsyncSession, sql: str, **p: Any) -> list[dict[str, Any]]:
    return [dict(r._mapping) for r in await s.execute(text(sql), p)]


async def transitions(s: AsyncSession, frm: datetime, to: datetime) -> list[dict[str, Any]]:
    return await _all(
        s, "SELECT * FROM analytics.v_transitions WHERE at >= :f AND at < :t", f=frm, t=to
    )


async def events_by_ids(s: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, Any]]:
    rows = await _all(s, "SELECT * FROM analytics.v_events WHERE id = ANY(:ids)", ids=ids)
    return {r["id"]: r for r in rows}


async def events_new(s: AsyncSession, frm: datetime, to: datetime) -> list[dict[str, Any]]:
    return await _all(
        s,
        "SELECT * FROM analytics.v_events WHERE first_seen_at >= :f AND first_seen_at < :t",
        f=frm,
        t=to,
    )


async def activity(s: AsyncSession, frm: datetime, to: datetime) -> list[dict[str, Any]]:
    return await _all(
        s,
        "SELECT user_id, at FROM analytics.v_activity WHERE at >= :f AND at < :t ORDER BY user_id, at",
        f=frm,
        t=to,
    )


async def drafts_for(s: AsyncSession, event_ids: list[uuid.UUID]) -> list[dict[str, Any]]:
    return await _all(
        s,
        "SELECT * FROM analytics.v_draft_versions WHERE event_id = ANY(:ids) ORDER BY draft_id, n",
        ids=event_ids,
    )


async def first_sources(s: AsyncSession, event_ids: list[uuid.UUID]) -> list[dict[str, Any]]:
    return await _all(
        s, "SELECT * FROM analytics.v_first_sources WHERE event_id = ANY(:ids)", ids=event_ids
    )


async def add_heartbeat(
    s: AsyncSession, user_id: uuid.UUID, event_id: uuid.UUID | None, now: datetime
) -> bool:
    """Не чаще раза в минуту на пользователя."""
    res = await s.execute(
        text(
            "INSERT INTO analytics.view_heartbeats (user_id, event_id, at) SELECT :u, :e, :n WHERE NOT EXISTS"
            " (SELECT 1 FROM analytics.view_heartbeats WHERE user_id = :u AND at > CAST(:n AS timestamptz) - interval '1 minute')"
        ),
        {"u": user_id, "e": event_id, "n": now},
    )
    return bool(res.rowcount)  # type: ignore[attr-defined]


async def purge_heartbeats(s: AsyncSession, before: datetime) -> int:
    res = await s.execute(
        text("DELETE FROM analytics.view_heartbeats WHERE at < :b"), {"b": before}
    )
    return int(res.rowcount or 0)  # type: ignore[attr-defined]
