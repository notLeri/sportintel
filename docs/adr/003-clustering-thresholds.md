# ADR-003. Clustering thresholds

- **Status:** accepted (provisional, until real data is labelled)
- **Date:** 2026-10-08
- **Affects:** candidate scoring, `events.cluster_article`, cluster evals, `app_settings.clustering`

## Context

A candidate's score is compared with the thresholds `t_high` (attach) and `t_low` (below it, a new event; between them, the grey zone). Under ADR-004 the main mode is **lexical** (no embeddings):
`score = (w_lex·lex + w_entities·jaccard + w_competition·same_comp) / (w_lex + w_entities + w_competition)`,
where `lex` is the `pg_trgm.similarity` of the titles. The original thresholds 0.82 / 0.60 were designed for embedding cosine similarity. For the lexical score they are too strict: paraphrases of the same fact almost never reach 0.82.

## Data and method

- `evals/datasets/clustering_v1.jsonl` is a **synthetic** set: 51 titles, 23 facts, paraphrases by different outlets and 5 hard negatives (the same teams, a different fact within 72 h). The labels were made by an assistant.
- The replay in `tests/evals/clustering.py` runs in memory, in `discovered_at` order, and uses **the same** `clustering.score/decide`. The similarity function reproduces pg_trgm semantics (covered by a unit test).
- Grid: `w_lex ∈ {0.3, 0.5, 0.7, 1.0}`, `lex_min ∈ {0.2, 0.3}`, `t_high` from 0.40 to 0.90 in steps of 0.01, `t_low = t_high − 0.2`. Criterion: max B-cubed F1 with false merges ≤ 3 %.
- Robustness: the same run with "degraded" entities (players removed, as if missing from the reference data). The choice is based on the worse of the two F1 values.

## Decision (lexical mode)

| Parameter | Before | After |
|---|---|---|
| `w_lex` | 0.5 | 0.5 |
| `lex_min` | 0.3 | **0.2** |
| `t_high` | 0.82 | **0.58** |
| `t_low` | 0.60 | **0.38** |

Result on clustering_v1: B-cubed F1 0.946 (P 0.90, R 1.00), false merges 1.2 %, grey-zone share 6 %. The worst F1 with degraded entities is 0.928. With the old thresholds F1 was 0.706: articles about one fact were split into separate events.

The values are the defaults of the `Clustering` schema in `platform/settings_store.py`. `app_settings` stores only overrides, so no separate seed migration is needed. An admin can change the thresholds without a redeploy.

## Consequences and risks

- The set is small and synthetic, so the numbers are optimistic. The main risk is **false merges of different facts about the same match** (preview and result). The remaining merges in the set are exactly of this kind. Mitigation: manual split/move and `possible_duplicate` links.
- **Embedding mode** uses a different score scale. When `ai_routing.embeddings=on` is enabled, the thresholds must be recalibrated (`--grid` on a set with embeddings). Until then the reference point is 0.82 / 0.60 (see the unit test).

## When to revisit

- Real data has been labelled (`scripts/export_clustering_dataset.py --from … --days 10`, column `gold_cluster`): rerun `make evals` and update the table.
- In a pilot, the share of manual merges or splits exceeds 10 %.
