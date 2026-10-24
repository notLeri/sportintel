import json
from pathlib import Path

import pytest
from tests.evals import metrics
from tests.evals.dataset import DatasetError, from_csv, load_enrich


def test_classification_metrics() -> None:
    gold, pred = ["HIGH", "HIGH", "LOW", "MEDIUM"], ["HIGH", "LOW", "LOW", "HIGH"]
    assert metrics.accuracy(gold, pred) == 0.5
    assert metrics.recall_of("HIGH", gold, pred) == 0.5
    assert metrics.precision_of("HIGH", gold, pred) == 0.5
    assert metrics.macro_f1(gold, pred) == pytest.approx((0.5 + 2 / 3 + 0) / 3)
    assert metrics.set_pr([{"a", "b"}], [{"a", "c", "d"}]) == (1 / 3, 1 / 2)


def test_bcubed_known_example() -> None:
    # Amigó et al.: gold {1,2,3},{4,5}; pred {1,2},{3,4,5}
    p, r, f = metrics.bcubed([1, 1, 1, 2, 2], ["a", "a", "b", "b", "b"])
    assert p == pytest.approx((1 + 1 + 1 / 3 + 2 / 3 + 2 / 3) / 5)
    assert r == pytest.approx((2 / 3 + 2 / 3 + 1 / 3 + 1 + 1) / 5)
    assert f == pytest.approx(2 * p * r / (p + r))
    assert metrics.false_merge_rate([1, 1, 1, 2, 2], ["a", "a", "b", "b", "b"]) == pytest.approx(
        2 / 6
    )
    assert metrics.bcubed([1, 2], [1, 2]) == (1.0, 1.0, 1.0)


def test_dataset_validation_and_csv(tmp_path: Path) -> None:
    bad = tmp_path / "bad.jsonl"
    bad.write_text(json.dumps({"title": "x", "gold": {"sport": "football"}}) + "\n")
    with pytest.raises(DatasetError, match=r"bad\.jsonl:1"):
        load_enrich(bad)
    src = tmp_path / "in.csv"
    src.write_text(
        "id,title,gold_sport,gold_relevance,gold_entities,gold_is_rumor\n1,T,football,high,Flamengo|Pedro,sim\n"
    )
    assert from_csv(src, tmp_path / "out.jsonl") == 1
    row = load_enrich(tmp_path / "out.jsonl")[0]
    assert row["gold"] == {
        "sport": "football",
        "relevance": "HIGH",
        "entities": ["Flamengo", "Pedro"],
        "is_rumor": True,
    }


def test_trigram_similarity_matches_pg_trgm_semantics() -> None:
    from tests.evals.clustering import similarity, trigrams

    assert trigrams("Cat") == {"  c", " ca", "cat", "at "}
    assert similarity("Lesão", "lesao") == 1.0
    assert similarity("abc", "xyz") == 0.0
