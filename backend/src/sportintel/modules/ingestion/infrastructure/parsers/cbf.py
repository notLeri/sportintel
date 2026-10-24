"""Профиль CBF (kind=html, tier OFFICIAL).

На 2026-10-07 cbf.com.br рендерит список новостей на клиенте (Next.js) — в HTML ссылок нет,
поэтому профиль проверен только на синтетической странице-списке (fixtures/sources/cbf).
Подключать источник CBF можно, когда появится серверный список или разрешённый фид.
"""

from sportintel.modules.ingestion.infrastructure.parsers.html_links import HtmlLinksProfile

CBF = HtmlLinksProfile(
    name="cbf",
    path_pattern=r"^/(?:futebol-brasileiro|selecao-brasileira|a-cbf)/noticias/(?:[a-z0-9-]+/)*[a-z0-9-]{12,}$",
)
