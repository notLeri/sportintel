import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser

from sportintel.modules.ingestion.domain.values import ArticleState

TITLE_MAX = 500


@dataclass(frozen=True)
class NewArticle:
    source_id: uuid.UUID
    canonical_url: str
    original_url: str
    title: str
    lead: str | None
    published_at: datetime | None
    image_url: str | None
    author: str | None
    manual: bool = False
    added_by: uuid.UUID | None = None
    target_event_id: uuid.UUID | None = None


@dataclass(frozen=True)
class Article:
    id: uuid.UUID
    source_id: uuid.UUID
    canonical_url: str
    original_url: str
    title: str
    lead: str | None
    published_at: datetime | None
    discovered_at: datetime
    image_url: str | None
    author: str | None
    language: str | None
    content_hash: int | None
    duplicate_of: uuid.UUID | None
    manual: bool
    added_by: uuid.UUID | None
    target_event_id: uuid.UUID | None
    state: ArticleState
    state_changed_at: datetime
    failure_code: str | None
    failure_detail: str | None


def clip_words(text: str, limit: int) -> str:
    """Обрезка по границе слова (без многоточия: текст — данные, не оформление)."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    space = cut.rfind(" ")
    return (cut[:space] if space > limit // 2 else cut).rstrip(" ,;:-")


class _TextOnly(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._skip += 1
        elif tag in {"br", "p", "div", "li"}:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    """Текст без разметки: HTML из лент не сохраняется (BE-T1.6 §15)."""
    parser = _TextOnly()
    parser.feed(html)
    parser.close()
    return re.sub(r"\s+", " ", "".join(parser.parts)).strip()
