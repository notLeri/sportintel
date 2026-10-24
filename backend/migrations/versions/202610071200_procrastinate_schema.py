"""procrastinate schema (Procrastinate 3.10.0, frozen copy)

Revision ID: 202610071200
Revises: 202610031700
Create Date: 2026-10-07 12:00:00+00:00
"""

from collections.abc import Sequence
from pathlib import Path

from alembic import op

revision: str = "202610071200"
down_revision: str | None = "202610031700"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Замороженная копия procrastinate/sql/schema.sql: обновление библиотеки — новая миграция
# с её migration-скриптами, а не изменение этой (BE-T0.5 §10).
SCHEMA_SQL = Path(__file__).resolve().parents[1] / "sql" / "procrastinate_3.10.0_schema.sql"


def upgrade() -> None:
    bind = op.get_bind()
    bind.exec_driver_sql("CREATE SCHEMA IF NOT EXISTS procrastinate")
    bind.exec_driver_sql("SET LOCAL search_path TO procrastinate, public")
    # psycopg трактует % как плейсхолдер даже без параметров → экранируем.
    bind.exec_driver_sql(SCHEMA_SQL.read_text().replace("%", "%%"))
    # Функции и триггеры схемы обращаются к таблицам без префикса: закрепляем search_path у
    # самих функций, чтобы DELETE/UPDATE из любого соединения (e2e-reset, SQL оператора) работали.
    bind.exec_driver_sql(
        """
        DO $$
        DECLARE f regprocedure;
        BEGIN
          FOR f IN SELECT p.oid::regprocedure FROM pg_proc p
                   JOIN pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname = 'procrastinate'
          LOOP
            EXECUTE format('ALTER FUNCTION %%s SET search_path = procrastinate, public', f);
          END LOOP;
        END $$
        """
    )
    bind.exec_driver_sql("SET LOCAL search_path TO DEFAULT")


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS procrastinate CASCADE")
