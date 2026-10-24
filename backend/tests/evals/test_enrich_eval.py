from pathlib import Path

import pytest
from tests.evals import enrich, report
from tests.evals.dataset import load_enrich

from sportintel.platform import settings_store
from sportintel.platform.db import Database

pytestmark = pytest.mark.evals
DATASET = Path(__file__).resolve().parents[3] / "evals" / "datasets" / "enrich_v1.jsonl"
TARGETS = {"accuracy_sport": 0.9, "recall_high": 0.8}


async def test_enrich_rules_baseline(db: Database) -> None:
    settings_store.clear_cache()
    rows = load_enrich(DATASET)
    pred = await enrich.predict_rules(db, rows)
    summary = enrich.score(rows, pred)
    misses = [
        f"{r['title']} — gold {r['gold']['sport']}/{r['gold']['relevance']}, got {p['sport']}/{p['relevance']} ({p['rationale']})"
        for r, p in zip(rows, pred, strict=True)
        if (r["gold"]["sport"], r["gold"]["relevance"]) != (p["sport"], p["relevance"])
    ]
    path = report.write(
        "enrich_v1_rules", "Evals обогащения: enrich_v1, режим rules", summary, TARGETS, misses
    )
    print(f"\nreport: {path}\n{summary}")
