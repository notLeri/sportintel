"""platform bootstrap: extensions, module schemas, pt_unaccent FTS, immutable_unaccent

Revision ID: 202610031700
Revises:
Create Date: 2026-10-03 17:00:00+00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "202610031700"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EXTENSIONS = ("vector", "pg_trgm", "unaccent", "citext")
SCHEMAS = (
    "identity",
    "sources",
    "ingestion",
    "taxonomy",
    "intelligence",
    "events",
    "editorial",
    "audit",
    "analytics",
    "platform",
)


def upgrade() -> None:
    # Нет `vector` у провайдера → CREATE EXTENSION падает с «extension "vector" is not
    # available» — сигнал для INFRA-T0.12.
    for ext in EXTENSIONS:
        op.execute(f'CREATE EXTENSION IF NOT EXISTS "{ext}" WITH SCHEMA public')
    for schema in SCHEMAS:
        op.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    op.execute("CREATE TEXT SEARCH CONFIGURATION public.pt_unaccent (COPY = portuguese)")
    op.execute(
        "ALTER TEXT SEARCH CONFIGURATION public.pt_unaccent "
        "ALTER MAPPING FOR hword, hword_part, word WITH public.unaccent, portuguese_stem"
    )
    op.execute(
        "CREATE FUNCTION platform.immutable_unaccent(text) RETURNS text "
        "LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT "
        "AS $$ SELECT public.unaccent('public.unaccent', $1) $$"
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS platform.immutable_unaccent(text)")
    op.execute("DROP TEXT SEARCH CONFIGURATION IF EXISTS public.pt_unaccent")
    for schema in reversed(SCHEMAS):
        op.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
    for ext in reversed(EXTENSIONS):
        op.execute(f'DROP EXTENSION IF EXISTS "{ext}"')
