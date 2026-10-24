"""sources: seed from migrations/seed/sources.csv

Revision ID: 202610071510
Revises: 202610071500
Create Date: 2026-10-07 15:10:00+00:00
"""

import csv
import uuid
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "202610071510"
down_revision: str | None = "202610071500"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEED = Path(__file__).resolve().parents[1] / "seed" / "sources.csv"
# Детерминированные id: повтор seed и downgrade находят те же строки.
NAMESPACE = uuid.UUID("6f1d3a52-0b1e-4c8e-9a51-5e3f3c0a1b01")

table = sa.table(
    "sources",
    sa.column("id", pg.UUID(as_uuid=True)),
    sa.column("name", sa.Text()),
    sa.column("domain", sa.Text()),
    sa.column("base_url", sa.Text()),
    sa.column("kind", sa.Text()),
    sa.column("feed_urls", pg.ARRAY(sa.Text())),
    sa.column("tier", sa.Text()),
    sa.column("owner_group", sa.Text()),
    sa.column("parser_profile", sa.Text()),
    sa.column("poll_interval_seconds", sa.Integer()),
    schema="sources",
)


def _rows() -> list[dict[str, object]]:
    with SEED.open(encoding="utf-8") as f:
        return [
            {
                "id": uuid.uuid5(NAMESPACE, r["domain"]),
                "name": r["name"],
                "domain": r["domain"],
                "base_url": r["base_url"],
                "kind": r["kind"],
                "feed_urls": [u for u in r["feed_urls"].split("|") if u],
                "tier": r["tier"] or None,
                "owner_group": r["owner_group"] or None,
                "parser_profile": r["parser_profile"] or "default",
                "poll_interval_seconds": int(r["poll_interval_seconds"] or 300),
            }
            for r in csv.DictReader(f)
        ]


def upgrade() -> None:
    rows = _rows()
    if rows:
        op.bulk_insert(table, rows)


def downgrade() -> None:
    ids = [row["id"] for row in _rows()]
    if ids:
        op.execute(table.delete().where(table.c.id.in_(ids)))
