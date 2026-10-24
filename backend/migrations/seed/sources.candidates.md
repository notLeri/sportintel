# Source candidates (not in the seed)

Checked on 2026-10-07 with a single `SportIntelBot/1.0` request. Only sources with a working RSS feed made it into `sources.csv`.
The product owner confirms the seed list; other sources are added through the API or the admin UI.

| Source | What was checked | Status |
|---|---|---|
| ge.globo.com | `https://ge.globo.com/rss/ge/`: 200, RSS, 95 items | **in seed** (tier A, globo) |
| cnnbrasil.com.br | `https://www.cnnbrasil.com.br/feed/`: 200, RSS, 60 items (general feed, not only sport; enrichment filters it) | **in seed** (tier B, cnn_br) |
| cbf.com.br | `https://www.cbf.com.br/futebol-brasileiro/noticias`: 200 HTML, but the list is rendered on the client (Next.js): no links in the HTML; sitemap and RSS return 404 | the `cbf` profile is ready, but the current site yields an empty list; waits for a server-rendered list or a permitted feed |
| espn.com.br | `/espn/rss/news`, `/rss`: 202 (anti-bot protection) | do not connect without permission |
| lance.com.br | `/feed/`, `/rss.xml`, `/rss`: 404/410 | no feed; a sitemap may work |
| esporte.uol.com.br | `https://rss.uol.com.br/feed/esporte.xml`: unstable response (ISO-8859-1) | recheck |
