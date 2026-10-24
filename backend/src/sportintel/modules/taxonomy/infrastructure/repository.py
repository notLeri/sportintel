import uuid
from collections.abc import Collection
from datetime import datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from sportintel.modules.taxonomy.domain.entity import Entity
from sportintel.modules.taxonomy.domain.linking import Candidate
from sportintel.modules.taxonomy.domain.values import EntityKind, EntityReviewState
from sportintel.modules.taxonomy.infrastructure.tables import entities, entity_aliases, sports
from sportintel.platform.ids import new_id
from sportintel.platform.text import normalize_name


class SqlTaxonomyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_sports(self, active_only: bool = True) -> list[dict[str, Any]]:
        q = select(sports).order_by(sports.c.sort, sports.c.id)
        if active_only:
            q = q.where(sports.c.active.is_(True))
        return [dict(r._mapping) for r in await self.session.execute(q)]

    async def add_entity(self, e: Entity) -> Entity:
        """canonical_name всегда становится и алиасом (BE-T2.1 §7)."""
        await self.session.execute(
            pg_insert(entities).values(
                id=e.id,
                kind=e.kind.value,
                sport_id=e.sport_id,
                canonical_name=e.canonical_name,
                name_norm=e.name_norm,
                country=e.country,
                external_ids=e.external_ids,
                priority=e.priority,
                auto_created=e.auto_created,
                review_state=e.review_state.value,
                active=e.active,
            )
        )
        await self.add_aliases(e.id, [e.canonical_name, *e.aliases])
        return e

    async def add_aliases(self, entity_id: uuid.UUID, aliases: Collection[str]) -> None:
        rows = {normalize_name(a): a for a in aliases if a.strip()}
        if rows:
            await self.session.execute(
                pg_insert(entity_aliases)
                .values(
                    [{"entity_id": entity_id, "alias": a, "alias_norm": n} for n, a in rows.items()]
                )
                .on_conflict_do_nothing()
            )

    async def search(
        self,
        key: str,
        limit: int,
        threshold: float,
        kind: str | None = None,
        sport: str | None = None,
        prefix: bool = False,
    ) -> list[tuple[uuid.UUID, float]]:
        """Сущности по алиасу: точное совпадение или trigram ≥ threshold, лучшие первыми."""
        if not key:
            return []
        await self.session.execute(
            text("SELECT set_config('pg_trgm.similarity_threshold', :t, true)"),
            {"t": str(threshold)},
        )
        rows = await self.session.execute(
            text(
                "SELECT e.id, max(CASE WHEN a.alias_norm = :key THEN 1.0 WHEN :prefix AND a.alias_norm LIKE :pat THEN 0.9 ELSE similarity(a.alias_norm, :key) END) AS sim"
                " FROM taxonomy.entity_aliases a JOIN taxonomy.entities e ON e.id = a.entity_id"
                " WHERE (a.alias_norm = :key OR a.alias_norm % :key OR (:prefix AND a.alias_norm LIKE :pat))"
                " AND e.active AND e.review_state <> 'ignored'"
                " AND (CAST(:kind AS text) IS NULL OR e.kind = :kind)"
                " AND (CAST(:sport AS text) IS NULL OR e.sport_id = :sport)"
                " GROUP BY e.id ORDER BY sim DESC, e.id LIMIT :limit"
            ),
            {
                "key": key,
                "kind": kind,
                "sport": sport,
                "limit": limit,
                "prefix": prefix,
                "pat": key.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%",
            },
        )
        return [(i, float(s)) for i, s in rows]

    async def get_many(self, ids: Collection[uuid.UUID]) -> list[dict[str, Any]]:
        if not ids:
            return []
        q = select(entities).where(entities.c.id.in_(list(ids)))
        return [dict(r._mapping) for r in await self.session.execute(q)]

    async def competition_aliases(self) -> list[tuple[str, list[str], str]]:
        q = (
            select(entities.c.canonical_name, entities.c.sport_id, entity_aliases.c.alias)
            .join(entity_aliases, entity_aliases.c.entity_id == entities.c.id)
            .where(entities.c.kind == EntityKind.COMPETITION.value, entities.c.active.is_(True))
            .order_by(entities.c.priority.desc(), entities.c.canonical_name, entity_aliases.c.alias)
        )
        grouped: dict[tuple[str, str], list[str]] = {}
        for name, sport, alias in await self.session.execute(q):
            grouped.setdefault((name, sport or ""), [])
            if alias != name:
                grouped[(name, sport or "")].append(alias)
        return [(n, a, s) for (n, s), a in list(grouped.items())[:300]]


class SqlLinkStore:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    _BASE = (
        "SELECT e.id, e.kind, e.sport_id, e.priority, a.alias_norm{sim}"
        " FROM taxonomy.entity_aliases a JOIN taxonomy.entities e ON e.id = a.entity_id"
        " WHERE e.active AND e.review_state <> 'ignored' AND {cond}"
    )

    @staticmethod
    def _cand(r: Any, sim: float = 1.0) -> Candidate:
        return Candidate(r.id, r.kind, r.sport_id, r.priority, sim, r.alias_norm)

    async def exact(self, keys: list[str]) -> list[Candidate]:
        q = text(self._BASE.format(sim="", cond="a.alias_norm = ANY(:keys)"))
        return [self._cand(r) for r in await self.session.execute(q, {"keys": keys})]

    async def trigram(
        self, key: str, kind: str, sport_id: str | None, threshold: float
    ) -> list[Candidate]:
        await self.session.execute(
            text("SELECT set_config('pg_trgm.similarity_threshold', :t, true)"),
            {"t": str(threshold)},
        )
        q = text(
            self._BASE.format(
                sim=", similarity(a.alias_norm, :key) AS sim",
                cond="a.alias_norm % :key AND e.kind = :kind",
            )
            + " AND (e.sport_id = :sport OR e.sport_id IS NULL OR CAST(:sport AS text) IS NULL)"
            " ORDER BY sim DESC, e.priority DESC, e.id LIMIT 5"
        )
        rows = await self.session.execute(q, {"key": key, "kind": kind, "sport": sport_id})
        best: dict[uuid.UUID, Candidate] = {}
        for r in rows:
            best.setdefault(r.id, self._cand(r, float(r.sim)))
        return list(best.values())

    async def create_player(self, name: str, sport_id: str) -> uuid.UUID:
        norm = normalize_name(name)
        row = await self.session.execute(
            text(
                "INSERT INTO taxonomy.entities (id, kind, sport_id, canonical_name, name_norm, auto_created, review_state)"
                " VALUES (:id, 'player', :s, :n, :nn, true, 'pending')"
                " ON CONFLICT (kind, coalesce(sport_id, ''), name_norm) DO NOTHING RETURNING id"
            ),
            {"id": new_id(), "s": sport_id, "n": name[:120], "nn": norm},
        )
        entity_id = row.scalar()
        if entity_id is None:  # гонка: игрока уже создала параллельная задача
            entity_id = (
                await self.session.execute(
                    text(
                        "SELECT id FROM taxonomy.entities WHERE kind='player' AND sport_id=:s AND name_norm=:nn"
                    ),
                    {"s": sport_id, "nn": norm},
                )
            ).scalar_one()
        await TaxRepo(self.session).add_aliases(entity_id, [name])
        return entity_id

    async def upsert_unlinked(
        self, mention: Any, norm: str, now: datetime, sample_article_id: uuid.UUID | None
    ) -> None:
        await self.session.execute(
            text(
                "INSERT INTO taxonomy.unlinked_mentions (mention_norm, kind, sport_key, sport_id, mention, occurrences,"
                " first_seen_at, last_seen_at, sample_article_id) VALUES (:n, :k, :sk, :s, :m, 1, :now, :now, :a)"
                " ON CONFLICT (mention_norm, kind, sport_key) DO UPDATE SET occurrences = taxonomy.unlinked_mentions.occurrences + 1,"
                " last_seen_at = :now, mention = :m"
            ),
            {
                "n": norm,
                "k": mention.kind.value,
                "sk": mention.sport_id or "",
                "s": mention.sport_id,
                "m": mention.text[:120],
                "now": now,
                "a": sample_article_id,
            },
        )


TaxRepo = SqlTaxonomyRepository


def entity_dto_row(m: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": m["id"],
        "kind": EntityKind(m["kind"]),
        "sport_id": m["sport_id"],
        "name": m["canonical_name"],
        "name_i18n": m.get("name_i18n") or {},
        "priority": m["priority"],
        "review_state": EntityReviewState(m["review_state"]),
    }
