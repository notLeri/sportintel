import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ManualArticleCreate(BaseModel):
    url: str = Field(max_length=2048)
    target_event_id: uuid.UUID | None = None


class ManualArticleAccepted(BaseModel):
    article_id: uuid.UUID
    created: bool
    state: str


class ArticleSourceRef(BaseModel):
    id: uuid.UUID
    name: str
    domain: str
    tier: str | None


class ArticleListItem(BaseModel):
    id: uuid.UUID
    title: str
    title_translated: str | None = None  # на языке интерфейса; None — перевода ещё нет
    url: str
    source: ArticleSourceRef | None
    published_at: datetime | None
    discovered_at: datetime
    state: str
    failure_code: str | None
    manual: bool
    image_url: str | None
    event_id: uuid.UUID | None  # BE-T2.15: заполняет composition через events.public
    sport_id: str | None = None  # BE-T2.8: из intelligence через composition
    relevance: str | None = None


class ArticleDetail(ArticleListItem):
    lead: str | None
    author: str | None
    language: str | None
    duplicate_of: uuid.UUID | None
    enrichment: dict[str, object] | None  # BE-T2.8


class ArticlePage(BaseModel):
    items: list[ArticleListItem]
    next_cursor: str | None
