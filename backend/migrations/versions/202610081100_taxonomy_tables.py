"""taxonomy: sports, entities, entity_aliases

Revision ID: 202610081100
Revises: 202610081000
Create Date: 2026-10-08 11:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "202610081100"
down_revision: str | None = "202610081000"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "sports",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name_i18n", pg.JSONB(), nullable=False),
        sa.Column("sort", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.CheckConstraint("id ~ '^[a-z0-9_]{2,32}$'", name="ck_sports_id"),
        sa.CheckConstraint("name_i18n ?& array['pt-BR','en','ru']", name="ck_sports_name_i18n"),
        schema="taxonomy",
    )
    op.create_table(
        "entities",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("sport_id", sa.Text(), sa.ForeignKey("taxonomy.sports.id"), nullable=True),
        sa.Column("canonical_name", sa.Text(), nullable=False),
        sa.Column("name_norm", sa.Text(), nullable=False),
        sa.Column("country", sa.Text(), nullable=True),
        sa.Column(
            "external_ids", pg.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("priority", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("auto_created", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("review_state", sa.Text(), nullable=False, server_default="approved"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "kind IN ('competition','team','player','coach','person','venue')",
            name="ck_entities_kind",
        ),
        sa.CheckConstraint("country ~ '^[A-Z]{2}$'", name="ck_entities_country"),
        sa.CheckConstraint("priority BETWEEN -1 AND 2", name="ck_entities_priority"),
        sa.CheckConstraint(
            "review_state IN ('approved','pending','ignored')", name="ck_entities_review_state"
        ),
        sa.CheckConstraint(
            "char_length(canonical_name) BETWEEN 1 AND 120", name="ck_entities_canonical_name"
        ),
        schema="taxonomy",
    )
    op.execute(
        "CREATE UNIQUE INDEX ux_entities_kind_sport_name_norm ON taxonomy.entities (kind, coalesce(sport_id, ''), name_norm)"
    )
    op.create_table(
        "entity_aliases",
        sa.Column(
            "entity_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("taxonomy.entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("alias", sa.Text(), nullable=False),
        sa.Column("alias_norm", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("entity_id", "alias_norm"),
        sa.CheckConstraint("char_length(alias) BETWEEN 1 AND 120", name="ck_entity_aliases_alias"),
        schema="taxonomy",
    )
    op.create_index(
        "ix_entity_aliases_alias_norm", "entity_aliases", ["alias_norm"], schema="taxonomy"
    )
    op.execute(
        "CREATE INDEX ix_entity_aliases_alias_norm_trgm ON taxonomy.entity_aliases USING gin (alias_norm gin_trgm_ops)"
    )


def downgrade() -> None:
    op.drop_table("entity_aliases", schema="taxonomy")
    op.drop_table("entities", schema="taxonomy")
    op.drop_table("sports", schema="taxonomy")
