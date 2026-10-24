"""Профиль kind=html: статьи — ссылки страницы-списка, чей путь подходит под регулярку."""

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from sportintel.modules.ingestion.domain.feed_item import FeedItem
from sportintel.modules.ingestion.infrastructure.extractor import ExtractedPage


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join("".join(self._text).split())))
            self._href = None


@dataclass(frozen=True)
class HtmlLinksProfile:
    """ponytail: регулярное выражение по пути; сложная вёрстка — selectolax (через ADR)."""

    name: str
    path_pattern: str
    min_title_chars: int = 15
    empty_list_is_error: bool = True

    def list_items(self, body: bytes, content_type: str, base_url: str) -> list[FeedItem]:
        parser = _Links()
        parser.feed(body.decode("utf-8", errors="replace"))  # stdlib: скрипты не исполняются
        pattern = re.compile(self.path_pattern)
        seen: dict[str, FeedItem] = {}
        for href, title in parser.links:
            url = urljoin(base_url, href)
            if pattern.search(urlsplit(url).path) and len(title) >= self.min_title_chars:
                seen.setdefault(url, FeedItem(url, title, None, None, None, None))
        return list(seen.values())

    def postprocess(self, page: ExtractedPage, html: bytes, url: str) -> ExtractedPage:
        return page
