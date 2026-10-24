"""In-memory реплей кластеризации (BE-T2.20) с тем же доменным кодом score/decide.

Лексический режим: похожесть заголовков считается как в pg_trgm (similarity по триграммам слов),
чтобы реплей не требовал БД.
"""

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from tests.evals import metrics

from sportintel.modules.events.domain.policies.clustering import (
    ArticleFeatures,
    CandidateRow,
    decide,
    score,
)
from sportintel.modules.events.domain.values import EventStatus
from sportintel.platform.settings_store import Clustering
from sportintel.platform.text import normalize_name

_WORD = re.compile(r"[^\W_]+")


def trigrams(s: str) -> set[str]:
    out: set[str] = set()
    for w in _WORD.findall(normalize_name(s)):
        padded = f"  {w} "
        out |= {padded[i : i + 3] for i in range(len(padded) - 2)}
    return out


def similarity(a: str, b: str) -> float:
    ta, tb = trigrams(a), trigrams(b)
    return len(ta & tb) / len(ta | tb) if ta | tb else 0.0


def _id(s: str | None) -> uuid.UUID | None:
    return uuid.uuid5(uuid.NAMESPACE_OID, s) if s else None


@dataclass
class _Event:
    id: uuid.UUID
    title: str
    sport: str | None
    competition: uuid.UUID | None
    entities: set[uuid.UUID] = field(default_factory=set)
    last_at: datetime | None = None


def replay(rows: list[dict[str, Any]], p: Clustering) -> tuple[list[uuid.UUID], int]:
    """→ (кластер каждой строки, число решений gray)."""
    events: list[_Event] = []
    by_article: dict[str, uuid.UUID] = {}
    clusters: list[uuid.UUID] = []
    gray = 0
    for r in sorted(rows, key=lambda r: r["discovered_at"]):
        at = datetime.fromisoformat(r["discovered_at"])
        ents = frozenset(e for e in map(_id, r["entity_ids"]) if e)
        feats = ArticleFeatures(
            r.get("embedding"), ents, _id(r.get("competition_id")), r.get("sport_id")
        )
        target: _Event | None = None
        if r.get("duplicate_of") and r["duplicate_of"] in by_article:
            target = next(e for e in events if e.id == by_article[r["duplicate_of"]])
        else:
            cands = []
            for e in events:
                if e.last_at and e.last_at < at - timedelta(hours=p.window_hours):
                    continue
                if e.sport and feats.sport_id and e.sport != feats.sport_id:
                    continue
                lex = similarity(r["title"], e.title)
                if lex >= p.lex_min or len(ents & e.entities) >= 2:
                    cands.append(
                        (
                            e,
                            CandidateRow(
                                e.id,
                                None,
                                e.competition,
                                frozenset(e.entities),
                                EventStatus.NEW,
                                lex,
                            ),
                        )
                    )
            scored = sorted(
                ((score(feats, c, False, p), e) for e, c in cands), key=lambda x: -x[0]
            )[: p.top_k]
            decision = decide(scored[0][0] if scored else None, p)
            gray += decision == "gray"
            if decision == "attach":
                target = scored[0][1]
        if target is None:
            target = _Event(uuid.uuid4(), r["title"], feats.sport_id, feats.competition_id)
            events.append(target)
        target.entities |= ents
        target.last_at = at
        by_article[r["article_id"]] = target.id
        clusters.append(target.id)
    return clusters, gray


def load(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    unlabeled = [i for i, r in enumerate(rows, start=1) if not r.get("gold_cluster")]
    if unlabeled:
        raise ValueError(f"{path.name}: unlabeled rows {unlabeled[:10]}")
    return sorted(rows, key=lambda r: r["discovered_at"])


def evaluate(rows: list[dict[str, Any]], p: Clustering) -> dict[str, float]:
    pred, gray = replay(rows, p)
    gold = [r["gold_cluster"] for r in rows]
    bp, br, bf = metrics.bcubed(gold, pred)
    return {
        "bcubed_p": bp,
        "bcubed_r": br,
        "bcubed_f1": bf,
        "false_merge_rate": metrics.false_merge_rate(gold, pred),
        "gray_rate": gray / len(rows) if rows else 0.0,
        "clusters": len(set(pred)),
        "gold_clusters": len(set(gold)),
    }


def grid(
    rows: list[dict[str, Any]], base: Clustering
) -> list[tuple[dict[str, float], dict[str, float]]]:
    """Перебор w_lex × lex_min × t_high (лексический режим); t_low влияет только на possible_duplicate."""
    out = []
    for w_lex in (0.3, 0.5, 0.7, 1.0):
        for lex_min in (0.2, 0.3):
            for t in range(40, 91):
                t_high = t / 100
                p = base.model_copy(
                    update={
                        "w_lex": w_lex,
                        "lex_min": lex_min,
                        "t_high": t_high,
                        "t_low": round(max(0.0, t_high - 0.2), 2),
                    }
                )
                out.append(
                    (
                        {"w_lex": w_lex, "lex_min": lex_min, "t_high": t_high, "t_low": p.t_low},
                        evaluate(rows, p),
                    )
                )
    return out


def best(
    results: list[tuple[dict[str, float], dict[str, float]]], max_false_merge: float = 0.03
) -> tuple[dict[str, float], dict[str, float]] | None:
    ok = [r for r in results if r[1]["false_merge_rate"] <= max_false_merge]
    # при равном F1 — более высокий порог (осторожнее склеивать)
    return max(ok, key=lambda r: (round(r[1]["bcubed_f1"], 4), r[0]["t_high"])) if ok else None
