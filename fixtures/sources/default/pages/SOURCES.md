# Фикстуры страниц (BE-T1.7)

Реальные страницы, сохранённые 2026-10-07 одним запросом `SportIntelBot/1.0`, только для contract-тестов извлечения.
Из HTML удалены `<script>` (кроме JSON-LD), `<style>` и комментарии — для размера; разметка и метаданные (`og:*`, JSON-LD) сохранены.

| Файл | URL |
|---|---|
| `ge_article.html` | https://ge.globo.com/futebol/times/fluminense/noticia/2026/10/07/cano-avanca-na-recuperacao-e-trabalha-com-bola-no-treino-do-fluminense.ghtml |
| `ge_article_2.html` | https://ge.globo.com/sc/surfe/noticia/2026/10/07/inscricoes-para-a-segunda-etapa-do-circuito-catarinense-de-surf-seguem-abertas.ghtml |
| `cnn_article.html` | https://www.cnnbrasil.com.br/esportes/automobilismo/carro-williams-ralf-schumacher-batalha-judicial-sumico-misterioso/ |

ESPN Brasil отдаёт антибот-страницу (HTTP 202), UOL — нестабильную ленту: их фикстур нет (см. `backend/migrations/seed/sources.candidates.md`).
Обновление фикстур — `backend/scripts/refresh_fixtures.py` (BE-T1.8).
