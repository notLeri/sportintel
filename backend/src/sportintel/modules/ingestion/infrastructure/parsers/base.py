"""Профиль парсинга источника (BE-T1.8): как получить список статей и поправить извлечение."""

from typing import Protocol

from sportintel.modules.ingestion.domain.feed_item import FeedItem
from sportintel.modules.ingestion.infrastructure.extractor import ExtractedPage


class ParserProfile(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def empty_list_is_error(self) -> bool:
        """Пустой список со страницы-списка (kind=html) — вероятная смена вёрстки → run error."""
        ...

    def list_items(self, body: bytes, content_type: str, base_url: str) -> list[FeedItem]: ...

    def postprocess(self, page: ExtractedPage, html: bytes, url: str) -> ExtractedPage: ...
