"""Загрузка и проверка датасетов; конвертация CSV разметки (BE-T2.9 §7, §11)."""

import csv
import json
from pathlib import Path
from typing import Any

LEVELS = {"HIGH", "MEDIUM", "LOW", "IRRELEVANT"}


class DatasetError(ValueError):
    pass


def load_enrich(path: Path) -> list[dict[str, Any]]:
    rows = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        gold = row.get("gold") or {}
        if "sport" not in gold or gold.get("relevance") not in LEVELS:
            raise DatasetError(f"{path.name}:{n}: gold.sport and gold.relevance are required")
        rows.append(row)
    return rows


def from_csv(src: Path, out: Path) -> int:
    """CSV из Google Sheets: id,url,source_name,source_tier,published_at,title,lead,text,gold_sport,gold_relevance,gold_entities(|),gold_is_rumor."""
    n = 0
    with src.open(encoding="utf-8") as f, out.open("w", encoding="utf-8") as o:
        for i, r in enumerate(csv.DictReader(f), start=2):
            if not r.get("gold_relevance") or r.get("gold_sport") is None:
                raise DatasetError(f"{src.name}:{i}: gold_sport and gold_relevance are required")
            row = {
                k: r.get(k) or None
                for k in (
                    "id",
                    "url",
                    "source_name",
                    "source_tier",
                    "published_at",
                    "title",
                    "lead",
                )
            }
            row["text"] = (r.get("text") or "")[:3000] or None
            row["gold"] = {
                "sport": r["gold_sport"] or None,
                "relevance": r["gold_relevance"].upper(),
                "entities": [
                    e.strip() for e in (r.get("gold_entities") or "").split("|") if e.strip()
                ],
                "is_rumor": (r.get("gold_is_rumor") or "").lower() in {"1", "true", "sim", "yes"},
            }
            o.write(json.dumps(row, ensure_ascii=False) + "\n")
            n += 1
    return n
