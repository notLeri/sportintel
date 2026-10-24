"""Извлечение текста и метаданных страницы через trafilatura (BE-T1.7)."""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import trafilatura

from sportintel.modules.ingestion.infrastructure.feeds import parse_date

_LANG_RE = re.compile(rb"<html[^>]*\blang=[\"']?([A-Za-z]{2,3}(?:-[A-Za-z]{2,4})?)", re.I)


@dataclass(frozen=True)
class ExtractedPage:
    title: str | None
    text: str | None
    description: str | None
    published_at: datetime | None
    image_url: str | None
    author: str | None
    language: str | None
    canonical_url: str | None


def _as_dict(result: Any) -> dict[str, Any]:
    if result is None:
        return {}
    return result.as_dict() if hasattr(result, "as_dict") else dict(result)


def extract(html: bytes, url: str) -> ExtractedPage:
    """CPU-задача: вызывается через asyncio.to_thread (CONV §15.3)."""
    doc = _as_dict(
        trafilatura.bare_extraction(
            html.decode("utf-8", errors="replace"),
            url=url,
            with_metadata=True,
            include_comments=False,
            include_tables=False,
            favor_precision=True,
        )
    )
    lang = doc.get("language")
    if not lang:
        m = _LANG_RE.search(html[:4096])
        lang = m.group(1).decode() if m else None
    text = (doc.get("text") or "").strip() or None
    return ExtractedPage(
        title=(doc.get("title") or None),
        text=text,
        description=(doc.get("description") or None),
        published_at=parse_date(doc.get("date")),
        image_url=(doc.get("image") or None),
        author=(doc.get("author") or None),
        language=lang,
        canonical_url=(doc.get("url") or None),
    )
