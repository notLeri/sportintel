"""Датасет для выбора модели брифов: N реальных событий (evidence pack) из БД.

uv run --env-file ../.env python scripts/export_brief_dataset.py --limit 20 --out ../evals/datasets/briefs_v1.jsonl
"""

import argparse
import asyncio
import json

from sqlalchemy import text

from sportintel.modules.events import public as events
from sportintel.platform.config import load_settings_or_exit
from sportintel.platform.db import Database

# Важные спортивные события с несколькими источниками — там бриф полезнее всего и сложнее.
PICK = text(
    "SELECT id FROM events.events WHERE status <> 'REJECTED' AND relevance IN ('HIGH', 'MEDIUM')"
    " AND sport_id IS NOT NULL ORDER BY source_count DESC, relevance_rank DESC, last_article_at DESC"
    " LIMIT :k"
)


async def main(limit: int) -> list[dict[str, object]]:
    db = Database(load_settings_or_exit().database_url, 2)
    rows = []
    async with db.uow() as uow:
        for (event_id,) in await uow.session.execute(PICK, {"k": limit}):
            pack = await events.build_evidence_pack(uow, event_id, 12)
            frag = {str(f.article_id): f.text for f in pack.fragments}
            rows.append(
                {
                    "event_id": str(event_id),
                    "title": pack.title,
                    "sport_id": pack.sport_id,
                    "sources": [
                        {
                            "article_id": str(s.article_id),
                            "source_name": s.source_name,
                            "tier": s.tier,
                            "url": s.url,
                            "title": s.title,
                            "lead": s.lead,
                            "fragment": frag.get(str(s.article_id)),
                        }
                        for s in pack.sources
                    ],
                }
            )
    await db.dispose()
    return rows


def write(rows: list[dict[str, object]], out: str) -> None:
    with open(out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{len(rows)} events → {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    write(asyncio.run(main(a.limit)), a.out)
