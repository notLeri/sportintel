# Eval datasets

## enrich_v1.jsonl: **temporary, synthetic**

60 headlines in the style of ge / CNN Brasil, written and labelled by an assistant following an editorial rubric
(HIGH: confirmed key news such as injuries and suspensions of key players, coach changes, decisive matches,
relegation, national-team call-ups; MEDIUM: line-ups, ordinary results, transfers; LOW: rumours,
lifestyle, advertising; IRRELEVANT: not sport). Article texts are not included (`text: null`).

The `enrich_rules` v2 rules were calibrated **on this same set**, so the metrics are inflated (overfitting).
Before a pilot, replace the set with real articles labelled by the product owner:

1. `scripts/export_eval_candidates.py --since … --limit 150 --out ../evals/candidates.csv` (staging/prod database);
2. fill in the `gold_*` columns in a spreadsheet and export a CSV;
3. `uv run python -m tests.evals.run from-csv candidates.csv ../evals/datasets/enrich_v1.jsonl`;
4. `make evals`, report in `evals/reports/`.
