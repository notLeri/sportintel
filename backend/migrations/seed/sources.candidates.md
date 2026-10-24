# Кандидаты в источники (не в seed)

Проверено 2026-10-07 одним запросом `SportIntelBot/1.0`. В `sources.csv` попали только источники с работающим RSS.
Состав seed подтверждает продукт (BE-T1.1 §10); остальные добавляются через API/админку.

| Источник | Что проверено | Статус |
|---|---|---|
| ge.globo.com | `https://ge.globo.com/rss/ge/` — 200, RSS, 95 items | **в seed** (tier A, globo) |
| cnnbrasil.com.br | `https://www.cnnbrasil.com.br/feed/` — 200, RSS, 60 items (общая лента, не только спорт: отсев — обогащение) | **в seed** (tier B, cnn_br) |
| cbf.com.br | `https://www.cbf.com.br/futebol-brasileiro/noticias` — 200 HTML, но список рендерится на клиенте (Next.js): ссылок в HTML нет; sitemap и RSS — 404 | профиль `cbf` готов (BE-T1.8), но с текущим сайтом даст пустой список; ждёт серверного списка или разрешённого фида |
| espn.com.br | `/espn/rss/news`, `/rss` — 202 (антибот-защита) | не подключать без разрешения |
| lance.com.br | `/feed/`, `/rss.xml`, `/rss` — 404/410 | ленты нет; возможен sitemap |
| esporte.uol.com.br | `https://rss.uol.com.br/feed/esporte.xml` — ответ нестабилен (ISO-8859-1) | перепроверить |
