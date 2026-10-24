import builtins
import json
import uuid
from collections.abc import Collection, Mapping
from dataclasses import fields
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import insert, literal, select, text, tuple_, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from sportintel.modules.sources.application.fetch_runs import FetchRunRecord
from sportintel.modules.sources.domain.errors import SourceDomainExists
from sportintel.modules.sources.domain.health import compute_health, next_poll_delay
from sportintel.modules.sources.domain.source import Source
from sportintel.modules.sources.domain.values import (
    ContentPolicy,
    SourceHealth,
    SourceKind,
    SourceTier,
)
from sportintel.modules.sources.infrastructure.fetch_runs_table import fetch_runs
from sportintel.modules.sources.infrastructure.tables import sources
from sportintel.platform.errors import ConcurrencyConflict

_FIELDS = [f.name for f in fields(Source)]
_ENUMS = {
    "kind": SourceKind,
    "tier": SourceTier,
    "content_policy": ContentPolicy,
    "health": SourceHealth,
}


def source_from_row(m: Mapping[str, Any]) -> Source:
    values: dict[str, Any] = {name: m[name] for name in _FIELDS}
    for name, enum in _ENUMS.items():
        if values[name] is not None:
            values[name] = enum(values[name])
    values["feed_urls"] = list(values["feed_urls"])
    values["url_keep_params"] = list(values["url_keep_params"])
    return Source(**values)


def _row(source: Source) -> dict[str, Any]:
    values = {name: getattr(source, name) for name in _FIELDS}
    for name in _ENUMS:
        if values[name] is not None:
            values[name] = values[name].value
    if values["next_poll_at"] is None:
        values.pop("next_poll_at")  # server_default now()
    return values


class SqlSourceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, source_id: uuid.UUID) -> Source | None:
        row = (await self.session.execute(select(sources).where(sources.c.id == source_id))).first()
        return source_from_row(dict(row._mapping)) if row else None

    async def get_many(self, ids: Collection[uuid.UUID]) -> builtins.list[Source]:
        if not ids:
            return []
        rows = await self.session.execute(select(sources).where(sources.c.id.in_(list(ids))))
        return [source_from_row(dict(r._mapping)) for r in rows]

    async def get_by_domain(self, domain: str) -> Source | None:
        row = (
            await self.session.execute(
                # ponytail: на домен несколько источников (каналы t.me) — берём корневой/первый;
                # точнее — сопоставлять URL статьи с base_url, когда понадобится.
                select(sources).where(sources.c.domain == domain).order_by(sources.c.base_url)
            )
        ).first()
        return source_from_row(dict(row._mapping)) if row else None

    async def list(self, active: bool | None = None) -> builtins.list[Source]:
        q = select(sources).order_by(sources.c.name)
        if active is not None:
            q = q.where(sources.c.active.is_(active))
        return [source_from_row(dict(r._mapping)) for r in await self.session.execute(q)]

    async def add(self, source: Source) -> None:
        try:
            async with self.session.begin_nested():
                await self.session.execute(insert(sources).values(**_row(source)))
        except IntegrityError as e:
            if "sources_domain_base_url_key" in str(e.orig):
                raise SourceDomainExists(
                    f"source {source.domain} ({source.base_url}) already exists"
                ) from None
            raise

    async def add_if_absent(self, source: Source) -> Source:
        """INSERT … ON CONFLICT DO NOTHING: безопасно при гонке двух ручных URL."""
        await self.session.execute(
            pg_insert(sources)
            .values(**_row(source))
            .on_conflict_do_nothing(index_elements=["domain", "base_url"])
        )
        q = select(sources).where(
            sources.c.domain == source.domain, sources.c.base_url == source.base_url
        )
        row = (await self.session.execute(q)).first()
        existing = source_from_row(dict(row._mapping)) if row else None
        assert existing is not None  # noqa: S101 — строка только что вставлена или уже была
        return existing

    async def update(self, source: Source, expected_version: int, now: datetime) -> Source:
        values = _row(source)
        values.pop("id")
        values["version"] = expected_version + 1
        values["updated_at"] = now
        row = (
            await self.session.execute(
                update(sources)
                .where(sources.c.id == source.id, sources.c.version == expected_version)
                .values(**values)
                .returning(*sources.c)
            )
        ).first()
        if row is None:
            current = await self.get(source.id)
            raise ConcurrencyConflict(
                current=None if current is None else {"version": current.version}
            )
        return source_from_row(dict(row._mapping))

    async def get_feed_cache(self, source_id: uuid.UUID) -> dict[str, Any]:
        q = select(sources.c.feed_cache).where(sources.c.id == source_id)
        return dict((await self.session.execute(q)).scalar() or {})

    async def set_feed_cache_entry(
        self, source_id: uuid.UUID, feed_url: str, etag: str | None, last_modified: str | None
    ) -> None:
        entry = {"etag": etag, "last_modified": last_modified}
        await self.session.execute(
            text(
                "UPDATE sources.sources SET feed_cache = feed_cache || jsonb_build_object("
                "CAST(:url AS text), CAST(:entry AS jsonb)) WHERE id = :id"
            ),
            {"url": feed_url, "entry": json.dumps(entry), "id": source_id},
        )

    async def mark_fetch_result(
        self, source_id: uuid.UUID, *, ok: bool, new_items: int, now: datetime
    ) -> None:
        """Факты опроса + backoff + health по последним 10 запускам (BE-T1.9).

        ok — хотя бы одна лента ok или not_modified: 304 — успех, backoff к нему не применяется.
        """
        current = await self.get(source_id)
        if current is None:
            return
        failures = 0 if ok else current.consecutive_failures + 1
        recent_q = (
            select(fetch_runs.c.status)
            .where(fetch_runs.c.source_id == source_id)
            .order_by(fetch_runs.c.started_at.desc(), fetch_runs.c.id.desc())
            .limit(10)
        )
        recent = [r[0] for r in await self.session.execute(recent_q)]
        delay = next_poll_delay(current.poll_interval_seconds, failures)
        values: dict[str, Any] = {
            "consecutive_failures": failures,
            "next_poll_at": now + timedelta(seconds=delay),
            "health": compute_health(recent, failures).value,
            "updated_at": now,
        }
        if ok:
            values["last_success_at"] = now
            if new_items > 0:
                values["last_new_article_at"] = now
        await self.session.execute(
            update(sources).where(sources.c.id == source_id).values(**values)
        )

    async def purge_fetch_runs(self, before: datetime, batch: int = 1000) -> int:
        removed = 0
        while True:
            result = await self.session.execute(
                text(
                    "DELETE FROM sources.fetch_runs WHERE id IN ("
                    "SELECT id FROM sources.fetch_runs WHERE started_at < :before LIMIT :batch)"
                ),
                {"before": before, "batch": batch},
            )
            n = int(result.rowcount or 0)  # type: ignore[attr-defined]
            removed += n
            if n < batch:
                return removed

    async def claim_due(self, now: datetime, limit: int = 50) -> builtins.list[uuid.UUID]:
        """Забрать источники к опросу: SKIP LOCKED — два планировщика не возьмут один источник."""
        rows = await self.session.execute(
            text(
                """
                UPDATE sources.sources AS s
                SET next_poll_at = :now + make_interval(secs => s.poll_interval_seconds)
                WHERE s.id IN (
                    SELECT id FROM sources.sources
                    WHERE active AND kind <> 'manual' AND next_poll_at <= :now
                    ORDER BY next_poll_at
                    LIMIT :limit
                    FOR UPDATE SKIP LOCKED
                )
                RETURNING s.id
                """
            ),
            {"now": now, "limit": limit},
        )
        return [r[0] for r in rows]


class SqlFetchRunStore:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def insert(self, run: "FetchRunRecord") -> None:
        values = dict(run.__dict__)
        values["error_detail"] = (run.error_detail or None) and run.error_detail[:500]
        await self.session.execute(insert(fetch_runs).values(**values))

    async def page(
        self, source_id: uuid.UUID, after: "tuple[datetime, uuid.UUID] | None", limit: int
    ) -> "builtins.list[FetchRunRecord]":
        q = select(fetch_runs).where(fetch_runs.c.source_id == source_id)
        if after is not None:
            q = q.where(
                tuple_(fetch_runs.c.started_at, fetch_runs.c.id)
                < tuple_(literal(after[0]), literal(after[1]))
            )
        q = q.order_by(fetch_runs.c.started_at.desc(), fetch_runs.c.id.desc()).limit(limit)
        return [FetchRunRecord(**dict(r._mapping)) for r in await self.session.execute(q)]
