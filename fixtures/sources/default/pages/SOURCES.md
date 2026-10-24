# Page fixtures

Real pages saved on 2026-10-07 with a single `SportIntelBot/1.0` request, used only by the extraction contract tests.
`<script>` (except JSON-LD), `<style>` and comments were stripped from the HTML to save space; markup and metadata (`og:*`, JSON-LD) are kept.

| File | URL |
|---|---|
| `ge_article.html` | https://ge.globo.com/futebol/times/fluminense/noticia/2026/10/07/cano-avanca-na-recuperacao-e-trabalha-com-bola-no-treino-do-fluminense.ghtml |
| `ge_article_2.html` | https://ge.globo.com/sc/surfe/noticia/2026/10/07/inscricoes-para-a-segunda-etapa-do-circuito-catarinense-de-surf-seguem-abertas.ghtml |
| `cnn_article.html` | https://www.cnnbrasil.com.br/esportes/automobilismo/carro-williams-ralf-schumacher-batalha-judicial-sumico-misterioso/ |

ESPN Brasil returns an anti-bot page (HTTP 202) and UOL an unstable feed, so they have no fixtures (see `backend/migrations/seed/sources.candidates.md`).
Refresh the fixtures with `backend/scripts/refresh_fixtures.py`.
