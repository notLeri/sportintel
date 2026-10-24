"""Датасет для калибровки кластеризации (BE-T2.20); gold_cluster размечает продукт.

uv run --env-file ../.env python scripts/export_clustering_dataset.py --from 2026-10-10 --days 10 --out ../evals/datasets/clustering_v1.jsonl
"""

import argparse
import asyncio
import json
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from sportintel.platform.config import load_settings_or_exit

SQL = text(
    "SELECT a.id, a.published_at, a.discovered_at, a.source_id, s.owner_group, s.tier, e.sport_id, e.competition_id,"
    " coalesce((SELECT array_agg(ae.entity_id::text) FROM intelligence.article_entities ae WHERE ae.article_id = a.id), '{}'),"
    " e.embedding::text, e.claims, a.title, a.lead, a.duplicate_of"
    " FROM ingestion.articles a JOIN sources.sources s ON s.id = a.source_id"
    " JOIN intelligence.article_enrichments e ON e.article_id = a.id"
    " WHERE a.discovered_at >= :since AND a.discovered_at < :until ORDER BY a.discovered_at"
)


def _iso(v: Any) -> Any:
    return v.isoformat() if isinstance(v, datetime) else (str(v) if v is not None else None)


async def fetch(since: date, days: int) -> list[Any]:
    engine = create_async_engine(load_settings_or_exit().database_url)
    async with engine.connect() as conn:
        rows = (
            await conn.execute(SQL, {"since": since, "until": since + timedelta(days=days)})
        ).all()
    await engine.dispose()
    return list(rows)


def main(since: date, days: int, out: str) -> None:
    keys = [
        "article_id",
        "published_at",
        "discovered_at",
        "source_id",
        "owner_group",
        "tier",
        "sport_id",
        "competition_id",
        "entity_ids",
        "embedding",
        "claims",
        "title",
        "lead",
        "duplicate_of",
    ]
    with open(out, "w", encoding="utf-8") as f:
        for r in asyncio.run(fetch(since, days)):
            row = dict(zip(keys, r, strict=True))
            row = {k: (v if k in {"entity_ids", "claims"} else _iso(v)) for k, v in row.items()}
            row["embedding"] = json.loads(row["embedding"]) if row["embedding"] else None
            f.write(json.dumps({**row, "gold_cluster": None}, ensure_ascii=False) + "\n")
    print(f"→ {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="since", type=date.fromisoformat, required=True)
    ap.add_argument("--days", type=int, default=10)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    main(a.since, a.days, a.out)
