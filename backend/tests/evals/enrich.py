"""Прогон обогащения на golden set (BE-T2.9). Режим rules — без сети; llm — фаза L."""

from datetime import datetime
from typing import Any

from tests.evals import metrics

from sportintel.modules.intelligence.application.rule_enrich import enrich_with_rules
from sportintel.modules.intelligence.domain.rules import ArticleInput
from sportintel.modules.taxonomy import public as taxonomy
from sportintel.platform.db import Database


async def predict_rules(db: Database, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    async with db.uow() as uow:
        for r in rows:
            a = ArticleInput(
                r.get("url") or "",
                r["title"],
                r.get("lead"),
                r.get("text"),
                (),
                "pt-BR",
                datetime.fromisoformat(r["published_at"]) if r.get("published_at") else None,
            )
            e = await enrich_with_rules(db, uow, a)
            ids = [
                m.entity_id
                for m in [*e.entities, *([e.competition] if e.competition else [])]
                if m.entity_id
            ]
            names = {d.name for d in (await taxonomy.get_entities(uow, ids)).values()}
            out.append(
                {
                    "sport": e.sport if e.is_sports else None,
                    "relevance": e.relevance.level.value,
                    "entities": names,
                    "is_rumor": bool(e.rumor_markers),
                    "rationale": e.relevance.rationale,
                }
            )
    return out


def score(rows: list[dict[str, Any]], pred: list[dict[str, Any]]) -> dict[str, float]:
    gs, ps = [r["gold"]["sport"] for r in rows], [p["sport"] for p in pred]
    gr, pr = [r["gold"]["relevance"] for r in rows], [p["relevance"] for p in pred]
    ep, er = metrics.set_pr(
        [set(r["gold"]["entities"]) for r in rows], [p["entities"] for p in pred]
    )
    return {
        "n": len(rows),
        "accuracy_sport": metrics.accuracy(gs, ps),
        "macro_f1_relevance": metrics.macro_f1(gr, pr),
        "recall_high": metrics.recall_of("HIGH", gr, pr),
        "precision_high": metrics.precision_of("HIGH", gr, pr),
        "entities_precision": ep,
        "entities_recall": er,
        "accuracy_rumor": metrics.accuracy(
            [r["gold"]["is_rumor"] for r in rows], [p["is_rumor"] for p in pred]
        ),
    }
