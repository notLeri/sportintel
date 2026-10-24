from dataclasses import dataclass

from sportintel.modules.ingestion.domain.feed_item import FeedItem
from sportintel.modules.ingestion.infrastructure.extractor import ExtractedPage
from sportintel.modules.ingestion.infrastructure.feeds import parse_feed


@dataclass(frozen=True)
class DefaultProfile:
    """RSS/Atom/sitemap-news + trafilatura без коррекций: новый RSS-источник — без кода."""

    name: str = "default"
    empty_list_is_error: bool = False  # пустая лента при 200 — «источник молчит», не ошибка

    def list_items(self, body: bytes, content_type: str, base_url: str) -> list[FeedItem]:
        return parse_feed(body, content_type, base_url)

    def postprocess(self, page: ExtractedPage, html: bytes, url: str) -> ExtractedPage:
        return page
