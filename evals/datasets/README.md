# Датасеты evals

## enrich_v1.jsonl — **временный, синтетический**

60 заголовков в стиле ge / CNN Brasil, написанных и размеченных ассистентом по редакционной рубрике
(HIGH — подтверждённые ключевые новости: травмы и дисквалификации основных игроков, смена тренера,
решающие матчи, вылет, вызов в сборную; MEDIUM — составы, рядовые результаты, трансферы; LOW — слухи,
быт, реклама; IRRELEVANT — не спорт). Тексты статей не включены (`text: null`).

Правила `enrich_rules` v2 калибровались **на этом же наборе**, так что метрики завышены (переобучение).
До пилота набор нужно заменить реальными статьями, размеченными продуктом:

1. `scripts/export_eval_candidates.py --since … --limit 150 --out ../evals/candidates.csv` (staging/prod БД);
2. разметить колонки `gold_*` в Google Sheets, выгрузить CSV;
3. `uv run python -m tests.evals.run from-csv candidates.csv ../evals/datasets/enrich_v1.jsonl`;
4. `make evals`, отчёт в `evals/reports/`.
