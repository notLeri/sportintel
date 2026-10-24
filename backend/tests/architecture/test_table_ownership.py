"""Каждый модуль пишет SQL только по своей схеме (CONV §7.2, BE-T2.11): чужие данные — через public.py."""

import re
from pathlib import Path

MODULES = Path(__file__).resolve().parents[2] / "src" / "sportintel" / "modules"
SCHEMAS = {
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
    "procrastinate",
}
SQL_REF = re.compile(r"\b(?:FROM|JOIN|INTO|UPDATE|TABLE)\s+(\w+)\.\w+", re.IGNORECASE)


def test_modules_touch_only_own_schema() -> None:
    violations = []
    for module in sorted(p for p in MODULES.iterdir() if p.is_dir() and not p.name.startswith("_")):
        for f in module.rglob("*.py"):
            for schema in SQL_REF.findall(f.read_text(encoding="utf-8")):
                if schema in SCHEMAS and schema != module.name:
                    violations.append(f"{f.relative_to(MODULES)}: {schema}")
    assert violations == []
