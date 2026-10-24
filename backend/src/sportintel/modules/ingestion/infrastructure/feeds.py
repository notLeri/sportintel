"""Разбор RSS/Atom (feedparser) и sitemap-news (defusedxml) → FeedItem (BE-T1.6)."""

import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import defusedxml.ElementTree as SafeET
import feedparser
import structlog

from sportintel.modules.ingestion.domain.feed_item import FeedItem

LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
_log = structlog.get_logger("sportintel.ingestion.feeds")
_ROOT_RE = re.compile(rb"<\s*(?:[\w-]+:)?(urlset|rss|feed|rdf:RDF|RDF)\b", re.IGNORECASE)
_NS = {
    "sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
    "news": "http://www.google.com/schemas/sitemap-news/0.9",
    "image": "http://www.google.com/schemas/sitemap-image/1.1",
}


class FeedParseError(Exception):
    """Лента не разобрана и не дала ни одного элемента (→ run error extract_empty)."""


def parse_date(raw: str | None) -> datetime | None:
    """RFC 822 (RSS) или ISO 8601 (Atom, sitemap). Без TZ — America/Sao_Paulo (§12)."""
    if not raw:
        return None
    raw = raw.strip()
    value: datetime | None = None
    try:
        value = parsedate_to_datetime(raw)
    except (TypeError, ValueError, IndexError):
        try:
            value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=LOCAL_TZ)
    return value


def _first_image(entry: Any) -> str | None:
    for media in entry.get("media_content", []) + entry.get("media_thumbnail", []):
        if media.get("url"):
            return str(media["url"])
    for enc in entry.get("enclosures", []):
        if str(enc.get("type", "")).startswith("image/") and enc.get("href"):
            return str(enc["href"])
    return None


def _parse_feedparser(body: bytes, content_type: str, base_url: str) -> list[FeedItem]:
    # bytes + content-type: иначе feedparser может ошибиться с кодировкой (§22).
    parsed = feedparser.parse(
        body, response_headers={"content-type": content_type or "application/xml"}
    )
    if parsed.bozo and not parsed.entries:
        raise FeedParseError(f"unparseable feed: {type(parsed.bozo_exception).__name__}")
    if parsed.bozo:
        _log.warning(
            "ingestion.feed_bozo",
            error=type(parsed.bozo_exception).__name__,
            items=len(parsed.entries),
        )
    items: list[FeedItem] = []
    for e in parsed.entries:
        url = e.get("link") or ""
        title = (e.get("title") or "").strip()
        if not url or not title:
            _log.debug("ingestion.feed_item_incomplete")
            continue
        summary = e.get("summary") or e.get("description")
        raw_date = e.get("published") or e.get("updated") or e.get("created")
        items.append(
            FeedItem(
                url=urljoin(base_url, url.strip()),
                title=title,
                summary=summary,
                published_at=parse_date(raw_date),
                image_url=_first_image(e),
                author=(e.get("author") or None),
            )
        )
    if parsed.bozo:
        # Битый XML: используем распознанные элементы; если валидных нет — ошибка ленты.
        error = type(parsed.bozo_exception).__name__
        if not items:
            raise FeedParseError(f"unparseable feed: {error}")
        _log.warning("ingestion.feed_bozo", error=error, items=len(items))
    return items


def _parse_sitemap_news(body: bytes, base_url: str) -> list[FeedItem]:
    try:
        root = SafeET.fromstring(body)  # defusedxml: без XXE и «billion laughs»
    except Exception as e:
        raise FeedParseError(f"unparseable sitemap: {type(e).__name__}") from None
    items: list[FeedItem] = []
    for node in root.findall("sm:url", _NS):
        loc = (node.findtext("sm:loc", default="", namespaces=_NS) or "").strip()
        news = node.find("news:news", _NS)
        title = (
            news.findtext("news:title", default="", namespaces=_NS) if news is not None else ""
        ) or ""
        if not loc or not title.strip():
            continue
        published = (
            news.findtext("news:publication_date", default=None, namespaces=_NS)
            if news is not None
            else None
        )
        image = node.findtext("image:image/image:loc", default=None, namespaces=_NS)
        items.append(
            FeedItem(
                url=urljoin(base_url, loc),
                title=title.strip(),
                summary=None,
                published_at=parse_date(published),
                image_url=image,
                author=None,
            )
        )
    return items


def parse_feed(body: bytes, content_type: str, base_url: str) -> list[FeedItem]:
    """Автоопределение по корню XML: urlset → sitemap-news, иначе RSS/Atom через feedparser."""
    head = body[:2048]
    m = _ROOT_RE.search(head)
    if m and m.group(1).lower() == b"urlset":
        return _parse_sitemap_news(body, base_url)
    return _parse_feedparser(body, content_type, base_url)
