# Source fixtures

Shared by the contract, integration and e2e tests (ARCHITECTURE §32). Some of them contain **third-party content**: only the pages the tests need are kept.

| Directory | Contents | Origin |
|---|---|---|
| `sources/default/` | `rss_ge.xml`, `atom_sample.xml`, `sitemap_news.xml` | synthetic feeds in the sources' formats |
| `sources/default/pages/` | `ge_article.html`, `ge_article_2.html`, `cnn_article.html` + `expected.json` | real pages from ge.globo.com and cnnbrasil.com.br, 2026-10-07 (see `pages/SOURCES.md`) |
| `sources/cbf/` | `list_page.html` + `expected.json` | a **synthetic** list page: the real cbf.com.br renders its list on the client |

Refresh: `cd backend && uv run python scripts/refresh_fixtures.py <profile> <url>…` prints the differences from `expected.json`.
