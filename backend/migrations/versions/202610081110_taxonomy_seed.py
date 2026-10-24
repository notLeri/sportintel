"""taxonomy: seed sports, competitions, teams (idempotent)

Revision ID: 202610081110
Revises: 202610081100
Create Date: 2026-10-08 11:10:00+00:00
"""

import csv
import json
import unicodedata
import uuid
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision: str = "202610081110"
down_revision: str | None = "202610081100"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SEED = Path(__file__).resolve().parents[1] / "seed"
NS = uuid.UUID("6f1d3a52-0b1e-4c8e-9a51-5e3f3c0a1b02")


def norm(s: str) -> str:
    # копия platform.text.normalize_name: миграция не импортирует код приложения
    d = unicodedata.normalize("NFKD", s)
    return " ".join("".join(c for c in d if not unicodedata.combining(c)).lower().split())


def _rows(name: str) -> list[dict[str, str]]:
    lines = [
        ln
        for ln in (SEED / name).read_text(encoding="utf-8").splitlines()
        if ln and not ln.startswith("#")
    ]
    return list(csv.DictReader(lines, delimiter=";"))


def _entities() -> list[tuple[uuid.UUID, str, str, str, int, str | None, list[str]]]:
    out = []
    for r in _rows("competitions.csv"):
        out.append(
            (
                uuid.uuid5(NS, f"competition:{r['canonical_name']}"),
                "competition",
                r["sport_id"],
                r["canonical_name"],
                int(r["priority"]),
                None,
                r["aliases"].split("|"),
            )
        )
    for r in _rows("teams.csv"):
        out.append(
            (
                uuid.uuid5(NS, f"team:{r['canonical_name']}"),
                "team",
                "football",
                r["canonical_name"],
                int(r["priority"]),
                "BR",
                r["aliases"].split("|"),
            )
        )
    return out


def upgrade() -> None:
    bind = op.get_bind()
    for r in _rows("sports.csv"):
        bind.execute(
            sa.text(
                "INSERT INTO taxonomy.sports (id, name_i18n, sort) VALUES (:id, CAST(:n AS jsonb), :s) ON CONFLICT DO NOTHING"
            ),
            {
                "id": r["id"],
                "n": json.dumps(
                    {"pt-BR": r["pt-BR"], "en": r["en"], "ru": r["ru"]}, ensure_ascii=False
                ),
                "s": int(r["sort"]),
            },
        )
    for eid, kind, sport, name, prio, country, aliases in _entities():
        bind.execute(
            sa.text(
                "INSERT INTO taxonomy.entities (id, kind, sport_id, canonical_name, name_norm, priority, country)"
                " VALUES (:id, :k, :s, :n, :nn, :p, :c) ON CONFLICT DO NOTHING"
            ),
            {
                "id": eid,
                "k": kind,
                "s": sport,
                "n": name,
                "nn": norm(name),
                "p": prio,
                "c": country,
            },
        )
        for alias in {name, *aliases}:
            bind.execute(
                sa.text(
                    "INSERT INTO taxonomy.entity_aliases (entity_id, alias, alias_norm) VALUES (:e, :a, :an) ON CONFLICT DO NOTHING"
                ),
                {"e": eid, "a": alias, "an": norm(alias)},
            )


def downgrade() -> None:
    ids = [e[0] for e in _entities()]
    op.get_bind().execute(
        sa.text("DELETE FROM taxonomy.entities WHERE id = ANY(:ids)"), {"ids": ids}
    )
    op.execute("DELETE FROM taxonomy.sports")
