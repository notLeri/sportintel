"""Учёт обращений к ИИ: что, для какого события, сколько длилось.

Из него — прогресс в интерфейсе («пишется пост, ~47 с») и нагрузка модели в аналитике.
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Literal

import structlog
from sqlalchemy import text

from sportintel.platform.db import Database

_log = structlog.get_logger("sportintel.ai_usage")
Kind = Literal["post", "rewrite", "translate", "translate_post", "brief"]
KINDS: tuple[Kind, ...] = ("post", "rewrite", "translate", "translate_post", "brief")
# Пока замеров нет: порядок величин для локальной модели (прогон 2026-10)
DEFAULT_S: dict[str, float] = {
    "post": 50,
    "rewrite": 50,
    "translate": 20,
    "translate_post": 15,
    "brief": 45,
}


@asynccontextmanager
async def track(
    db: Database, kind: Kind, model: str, event_id: uuid.UUID | None = None
) -> AsyncIterator[None]:
    """Запись открыта, пока идёт вызов: интерфейс видит, что именно сейчас пишет ИИ.
    Учёт не должен ронять сам вызов: ошибка записи только логируется."""
    call_id = None
    try:
        async with db.uow() as uow:
            call_id = (
                await uow.session.execute(
                    text(
                        "INSERT INTO platform.ai_calls (kind, event_id, model, started_at)"
                        " VALUES (:k, :e, :m, clock_timestamp()) RETURNING id"
                    ),
                    {"k": kind, "e": event_id, "m": model},
                )
            ).scalar_one()
    except Exception:
        _log.warning("ai_usage.start_failed", kind=kind)
    ok = False
    try:
        yield
        ok = True
    finally:
        if call_id is not None:
            try:
                async with db.uow() as uow:
                    await uow.session.execute(
                        text(
                            "UPDATE platform.ai_calls SET finished_at = clock_timestamp(), ok = :ok"
                            " WHERE id = :i"
                        ),
                        {"i": call_id, "ok": ok},
                    )
            except Exception:
                _log.warning("ai_usage.finish_failed", call_id=call_id)


async def running(session: Any) -> list[dict[str, Any]]:
    """Идущие сейчас вызовы: kind, event_id, elapsed_s. Незакрытая запись старше 10 минут
    (дольше любого таймаута модели) — оборванный процесс, её не показываем."""
    rows = await session.execute(
        text(
            "SELECT kind, event_id, extract(epoch FROM clock_timestamp() - started_at) AS elapsed_s"
            " FROM platform.ai_calls WHERE finished_at IS NULL"
            " AND started_at > clock_timestamp() - interval '10 minutes' ORDER BY started_at"
        )
    )
    return [dict(r._mapping) for r in rows]


async def stats(session: Any, frm: datetime, to: datetime) -> dict[str, dict[str, Any]]:
    """По видам: calls, failed, p50_s (успешных), busy_s (сумма времени модели), events."""
    rows = await session.execute(
        text(
            "SELECT kind, count(*) AS calls, count(*) FILTER (WHERE NOT ok) AS failed,"
            " percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM finished_at - started_at))"
            "  FILTER (WHERE ok) AS p50_s,"
            " coalesce(sum(extract(epoch FROM finished_at - started_at)), 0) AS busy_s,"
            " count(DISTINCT event_id) AS events"
            " FROM platform.ai_calls WHERE finished_at IS NOT NULL"
            " AND started_at >= :f AND started_at < :t GROUP BY kind"
        ),
        {"f": frm, "t": to},
    )
    return {
        r.kind: {
            "calls": r.calls,
            "failed": r.failed,
            "p50_s": float(r.p50_s) if r.p50_s is not None else None,
            "busy_s": float(r.busy_s),
            "events": r.events,
        }
        for r in rows
    }


async def recent_failed_share(session: Any, n: int = 20) -> float | None:
    """Доля упавших среди последних n завершённых вызовов; None — вызовов ещё не было."""
    row = (
        await session.execute(
            text(
                "SELECT count(*) AS calls, count(*) FILTER (WHERE NOT ok) AS failed FROM ("
                " SELECT ok FROM platform.ai_calls WHERE finished_at IS NOT NULL"
                " ORDER BY finished_at DESC LIMIT :n) x"
            ),
            {"n": n},
        )
    ).one()
    return row.failed / row.calls if row.calls else None


async def typical_s(session: Any) -> dict[str, float]:
    """Сколько обычно длится вызов каждого вида: медиана последних 50 успешных."""
    rows = await session.execute(
        text(
            "SELECT kind, percentile_cont(0.5) WITHIN GROUP (ORDER BY s) AS p50 FROM ("
            " SELECT kind, extract(epoch FROM finished_at - started_at) AS s,"
            "  row_number() OVER (PARTITION BY kind ORDER BY started_at DESC) AS rn"
            " FROM platform.ai_calls WHERE ok) x WHERE rn <= 50 GROUP BY kind"
        )
    )
    got = {r.kind: float(r.p50) for r in rows}
    return {k: round(got.get(k, DEFAULT_S[k]), 1) for k in KINDS}


async def done_since(session: Any, hours: int) -> dict[str, int]:
    """Сколько событий ИИ обработал за последние hours часов, по видам (время — БД)."""
    rows = await session.execute(
        text(
            "SELECT kind, count(DISTINCT coalesce(event_id::text, id::text)) FROM platform.ai_calls"
            " WHERE ok AND finished_at >= clock_timestamp() - make_interval(hours => :h)"
            " GROUP BY kind"
        ),
        {"h": hours},
    )
    return {r[0]: int(r[1]) for r in rows}


async def purge(session: Any, before: datetime) -> int:
    res = await session.execute(
        text("DELETE FROM platform.ai_calls WHERE started_at < :b"), {"b": before}
    )
    return int(res.rowcount or 0)
