# Фикстуры источников

Общие для contract-, integration- и e2e-тестов (ARCHITECTURE §32). Содержат **чужой контент**: храним только
необходимые страницы, только в этом репозитории, не публикуем (BE-T1.8 §22).

| Каталог | Что внутри | Происхождение |
|---|---|---|
| `sources/default/` | `rss_ge.xml`, `atom_sample.xml`, `sitemap_news.xml` | синтетические ленты в формате источников |
| `sources/default/pages/` | `ge_article.html`, `ge_article_2.html`, `cnn_article.html` + `expected.json` | реальные страницы ge.globo.com и cnnbrasil.com.br, 2026-10-07 (см. `pages/SOURCES.md`) |
| `sources/cbf/` | `list_page.html` + `expected.json` | **синтетическая** страница-список: реальный cbf.com.br рендерит список на клиенте |

Обновление: `cd backend && uv run python scripts/refresh_fixtures.py <profile> <url>…` — печатает расхождения с `expected.json`.
