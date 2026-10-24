import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.functions import coalesce as func_coalesce

from sportintel.modules.ingestion.domain.article import Article, NewArticle
from sportintel.modules.ingestion.domain.simhash import SYNDICATION_MAX_HAMMING
from sportintel.modules.ingestion.domain.values import ArticleState
from sportintel.modules.ingestion.infrastructure.content_table import article_content
from sportintel.modules.ingestion.infrastructure.tables import articles
from sportintel.platform.ids import new_id

BATCH = 200
_ARTICLE_COLS = [
    c for c in articles.c if c.name not in {"search_tsv", "created_at", "updated_at", "i18n"}
]


def article_from_row(m: Any) -> Article:
    values = {c.name: m[c.name] for c in _ARTICLE_COLS}
    values["state"] = ArticleState(values["state"])
    return Article(**values)


class SqlArticleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def insert_new(self, items: Sequence[NewArticle], now: datetime) -> list[uuid.UUID]:
        """Новые статьи; известные canonical_url пропускаются (ON CONFLICT DO NOTHING)."""
        created: list[uuid.UUID] = []
        for start in range(0, len(items), BATCH):
            rows = [
                {**item.__dict__, "id": new_id(), "discovered_at": now, "state_changed_at": now}
                for item in items[start : start + BATCH]
            ]
            result = await self.session.execute(
                pg_insert(articles)
                .values(rows)
                .on_conflict_do_nothing(index_elements=["canonical_url"])
                .returning(articles.c.id)
            )
            created.extend(r[0] for r in result)
        return created

    async def get(self, article_id: uuid.UUID) -> Article | None:
        row = (
            await self.session.execute(select(*_ARTICLE_COLS).where(articles.c.id == article_id))
        ).first()
        return article_from_row(row._mapping) if row else None

    async def get_many(self, ids: list[uuid.UUID]) -> list[Article]:
        if not ids:
            return []
        rows = await self.session.execute(select(*_ARTICLE_COLS).where(articles.c.id.in_(ids)))
        return [article_from_row(r._mapping) for r in rows]

    async def translations(
        self, ids: list[uuid.UUID], lang: str
    ) -> dict[uuid.UUID, dict[str, Any]]:
        q = select(articles.c.id, articles.c.i18n[lang]).where(
            articles.c.id.in_(ids), articles.c.i18n.has_key(lang)
        )
        return {r[0]: r[1] for r in await self.session.execute(q)} if ids else {}

    async def set_translation(
        self, article_id: uuid.UUID, lang: str, title: str, lead: str | None
    ) -> None:
        await self.session.execute(
            text(
                "UPDATE ingestion.articles SET i18n = i18n || jsonb_build_object(CAST(:l AS text),"
                " jsonb_build_object('title', CAST(:t AS text), 'lead', CAST(:d AS text)))"
                " WHERE id = :i"
            ),
            {"i": article_id, "l": lang, "t": title, "d": lead},
        )

    async def get_by_canonical(self, canonical_url: str) -> Article | None:
        q = select(*_ARTICLE_COLS).where(articles.c.canonical_url == canonical_url)
        row = (await self.session.execute(q)).first()
        return article_from_row(row._mapping) if row else None

    async def set_target_event(self, article_id: uuid.UUID, event_id: uuid.UUID) -> None:
        q = update(articles).where(articles.c.id == article_id).values(target_event_id=event_id)
        await self.session.execute(q)

    async def set_state(
        self,
        article_id: uuid.UUID,
        state: ArticleState,
        now: datetime,
        failure_code: str | None = None,
        failure_detail: str | None = None,
    ) -> None:
        await self.session.execute(
            update(articles)
            .where(articles.c.id == article_id)
            .values(
                state=state.value,
                state_changed_at=now,
                updated_at=now,
                failure_code=failure_code,
                failure_detail=(failure_detail or None) and failure_detail[:500],
            )
        )

    async def stuck_in_state(
        self, state: ArticleState, before: datetime, limit: int = 500
    ) -> list[uuid.UUID]:
        q = (
            select(articles.c.id)
            .where(articles.c.state == state.value, articles.c.state_changed_at < before)
            .order_by(articles.c.state_changed_at)
            .limit(limit)
        )
        return [r[0] for r in await self.session.execute(q)]

    async def fill_extracted(
        self, article_id: uuid.UUID, fields: dict[str, Any], now: datetime
    ) -> None:
        """Только пустые поля (BE-T1.7 §7.4): COALESCE оставляет уже известные значения."""
        values: dict[str, Any] = {"updated_at": now}
        for name in ("lead", "published_at", "image_url", "author", "language"):
            if fields.get(name) is not None:
                values[name] = func_coalesce(articles.c[name], fields[name])
        for name in ("content_hash", "duplicate_of", "title"):
            if name in fields:
                values[name] = fields[name]
        if fields.get("replace_lead"):  # лид из ленты оборван на полуслове — заменить
            values["lead"] = fields["lead"]
        await self.session.execute(
            update(articles).where(articles.c.id == article_id).values(**values)
        )

    async def save_content(
        self, article_id: uuid.UUID, body: str, now: datetime, ttl: timedelta
    ) -> None:
        stmt = pg_insert(article_content).values(
            article_id=article_id, text=body, extracted_at=now, expires_at=now + ttl
        )
        await self.session.execute(
            stmt.on_conflict_do_update(
                index_elements=["article_id"],
                set_={"text": stmt.excluded.text, "extracted_at": now, "expires_at": now + ttl},
            )
        )

    async def get_text(self, article_id: uuid.UUID, now: datetime) -> str | None:
        q = select(article_content.c.text).where(
            article_content.c.article_id == article_id, article_content.c.expires_at > now
        )
        return (await self.session.execute(q)).scalar()

    async def find_syndication_origin(
        self, article_id: uuid.UUID, source_id: uuid.UUID, content_hash: int, since: datetime
    ) -> uuid.UUID | None:
        """Самая ранняя почти-копия другого источника (Хэмминг ≤ 6) за окно."""
        row = await self.session.execute(
            text(
                """
                SELECT id FROM ingestion.articles
                WHERE id <> :id AND source_id <> :source_id
                  AND discovered_at > :since
                  AND content_hash IS NOT NULL AND duplicate_of IS NULL
                  AND bit_count((content_hash # :h)::bit(64)) <= :max_distance
                ORDER BY discovered_at, id
                LIMIT 1
                """
            ),
            {
                "id": article_id,
                "source_id": source_id,
                "since": since,
                "h": content_hash,
                "max_distance": SYNDICATION_MAX_HAMMING,
            },
        )
        return row.scalar()

    async def purge_expired_content(self, now: datetime, batch: int = 1000) -> int:
        # Результаты пробного fetch живут сутки (BE-T4.8).
        await self.session.execute(
            text("DELETE FROM ingestion.preview_results WHERE created_at < :t"),
            {"t": now - timedelta(days=1)},
        )
        removed = 0
        while True:
            result = await self.session.execute(
                text(
                    "DELETE FROM ingestion.article_content WHERE article_id IN ("
                    "SELECT article_id FROM ingestion.article_content"
                    " WHERE expires_at < :now LIMIT :batch)"
                ),
                {"now": now, "batch": batch},
            )
            n = int(result.rowcount or 0)  # type: ignore[attr-defined]
            removed += n
            if n < batch:
                return removed
