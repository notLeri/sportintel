from pathlib import Path

import pytest
from tests.evals import clustering, report

from sportintel.platform.settings_store import Clustering

pytestmark = pytest.mark.evals
DATASET = Path(__file__).resolve().parents[3] / "evals" / "datasets" / "clustering_v1.jsonl"


def test_clustering_lexical_grid() -> None:
    rows = clustering.load(DATASET)
    current = clustering.evaluate(rows, Clustering())
    results = clustering.grid(rows, Clustering())
    top = clustering.best(results)
    assert top is not None, "no setting keeps false merges ≤ 3 %"
    params, m = top
    summary = {
        **{f"current_{k}": v for k, v in current.items()},
        **{f"best_{k}": v for k, v in params.items()},
        **{f"best_{k}": v for k, v in m.items()},
    }
    path = report.write(
        "clustering_v1_lexical",
        "Evals кластеризации: clustering_v1, лексический режим",
        summary,
        {"best_bcubed_f1": 0.85},
        [],
    )
    print(f"\nreport: {path}\ncurrent={current}\nbest={params} {m}")
