"""Метрики evals (BE-T2.9, BE-T2.20). Чистые функции."""

from collections.abc import Hashable, Sequence


def accuracy(gold: Sequence[object], pred: Sequence[object]) -> float:
    return sum(g == p for g, p in zip(gold, pred, strict=True)) / len(gold) if gold else 0.0


def f1(tp: int, fp: int, fn: int) -> float:
    return 2 * tp / (2 * tp + fp + fn) if tp else 0.0


def macro_f1(gold: Sequence[str], pred: Sequence[str]) -> float:
    labels = sorted(set(gold))
    scores = [
        f1(
            sum(g == p == lb for g, p in zip(gold, pred, strict=True)),
            sum(p == lb != g for g, p in zip(gold, pred, strict=True)),
            sum(g == lb != p for g, p in zip(gold, pred, strict=True)),
        )
        for lb in labels
    ]
    return sum(scores) / len(scores) if scores else 0.0


def recall_of(label: str, gold: Sequence[str], pred: Sequence[str]) -> float:
    hits = [p == label for g, p in zip(gold, pred, strict=True) if g == label]
    return sum(hits) / len(hits) if hits else 0.0


def precision_of(label: str, gold: Sequence[str], pred: Sequence[str]) -> float:
    hits = [g == label for g, p in zip(gold, pred, strict=True) if p == label]
    return sum(hits) / len(hits) if hits else 0.0


def set_pr(gold: Sequence[set[str]], pred: Sequence[set[str]]) -> tuple[float, float]:
    tp = sum(len(g & p) for g, p in zip(gold, pred, strict=True))
    n_pred, n_gold = sum(map(len, pred)), sum(map(len, gold))
    return (tp / n_pred if n_pred else 0.0, tp / n_gold if n_gold else 0.0)


def bcubed(gold: Sequence[Hashable], pred: Sequence[Hashable]) -> tuple[float, float, float]:
    """B-cubed P/R/F1: для каждого элемента — доля общего в его кластерах."""
    n = len(gold)
    if not n:
        return 0.0, 0.0, 0.0
    p = r = 0.0
    for i in range(n):
        same_pred = [j for j in range(n) if pred[j] == pred[i]]
        same_gold = [j for j in range(n) if gold[j] == gold[i]]
        both = sum(gold[j] == gold[i] for j in same_pred)
        p += both / len(same_pred)
        r += both / len(same_gold)
    p, r = p / n, r / n
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def false_merge_rate(gold: Sequence[Hashable], pred: Sequence[Hashable]) -> float:
    """Доля пар с разным gold, попавших в один кластер."""
    n = len(gold)
    diff = [(i, j) for i in range(n) for j in range(i + 1, n) if gold[i] != gold[j]]
    return sum(pred[i] == pred[j] for i, j in diff) / len(diff) if diff else 0.0
