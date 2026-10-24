"""Кандидаты для golden set (BE-T2.9): CSV с пустыми колонками gold_* для разметки в Google Sheets.

uv run --env-file ../.env python scripts/export_eval_candidates.py --since 2026-10-01 --limit 150 --out ../evals/candidates.csv
Затем: python -m tests.evals.run from-csv ../evals/candidates.csv ../evals/datasets/enrich_v1.jsonl
"""

import argparse
import asyncio
import csv
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from sportintel.platform.config import load_settings_or_exit

SQL = text(
    "SELECT a.id, a.original_url, s.name, s.tier, a.published_at, a.title, a.lead, left(c.text, 3000)"
    " FROM ingestion.articles a JOIN sources.sources s ON s.id = a.source_id"
    " LEFT JOIN ingestion.article_content c ON c.article_id = a.id"
    " WHERE a.discovered_at >= :since AND a.duplicate_of IS NULL"
    " ORDER BY random() LIMIT :limit"
)
COLS = [
    "id",
    "url",
    "source_name",
    "source_tier",
    "published_at",
    "title",
    "lead",
    "text",
    "gold_sport",
    "gold_relevance",
    "gold_entities",
    "gold_is_rumor",
]


async def fetch(since: date, limit: int) -> list[Any]:
    engine = create_async_engine(load_settings_or_exit().database_url)
    async with engine.connect() as conn:
        rows = (await conn.execute(SQL, {"since": since, "limit": limit})).all()
    await engine.dispose()
    return list(rows)


def main(since: date, limit: int, out: str) -> None:
    rows = asyncio.run(fetch(since, limit))
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLS)
        for r in rows:
            w.writerow([*r[:4], r[4].isoformat() if r[4] else "", *r[5:], "", "", "", ""])
    print(f"{len(rows)} rows → {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", type=date.fromisoformat, required=True)
    ap.add_argument("--limit", type=int, default=150)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    main(a.since, a.limit, a.out)
