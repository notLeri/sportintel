import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, Field


class EntityRef(BaseModel):
    id: uuid.UUID
    name: str


class SourceRef(BaseModel):
    id: uuid.UUID
    name: str
    tier: str | None


class EventListItem(BaseModel):
    id: uuid.UUID
    title: str
    title_origin: str
    title_i18n: dict[str, str]  # перевод заголовка (из AI-брифа) по языкам UI
    relevance: str
    relevance_origin: str
    reliability: str
    reliability_origin: str
    status: str
    sport_id: str | None
    region: str | None  # ISO 3166-1 alpha-2
    competition: EntityRef | None
    article_count: int
    source_count: int
    independent_source_count: int
    top_sources: list[SourceRef]
    occurred_at: datetime
    last_article_at: datetime
    updated_at: datetime
    has_open_conflicts: bool
    has_updates_since_edit: bool
    stale_suspected: bool
    has_clickbait: bool
    assignee_id: uuid.UUID | None
    origin: str
    version: int


class EventPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    summary: str | None = Field(default=None, max_length=3000)
    sport_id: str | None = None
    competition_id: uuid.UUID | None = None
    team_ids: list[uuid.UUID] | None = Field(default=None, max_length=20)
    player_ids: list[uuid.UUID] | None = Field(default=None, max_length=30)


class ManualEventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    summary: str | None = Field(default=None, max_length=3000)
    sport_id: str | None = None
    competition_id: uuid.UUID | None = None
    team_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)
    player_ids: list[uuid.UUID] = Field(default_factory=list, max_length=30)
    urls: list[Annotated[str, Field(max_length=2048)]] = Field(default_factory=list, max_length=10)


class TransitionRequest(BaseModel):
    to: str
    reason: str | None = None
    comment: str | None = Field(default=None, max_length=500)


class EventPage(BaseModel):
    items: list[EventListItem]
    next_cursor: str | None


class Citation(BaseModel):
    n: int
    article_id: uuid.UUID


class SummaryOut(BaseModel):
    text: str
    translations: dict[str, str] = {}  # перевод на язык интерфейса (только для текущей сводки)
    origin: str | None
    citations: list[Citation]
    grounding: dict[str, Any] | None
    generated_at: datetime | None


class FactorOut(BaseModel):
    code: str
    detail: str = ""


class EntityKindRef(BaseModel):
    id: uuid.UUID
    kind: str
    name: str


class ArticleSource(BaseModel):
    id: uuid.UUID
    name: str
    tier: str | None
    owner_group: str | None
    health: str
    language: str = ""  # язык, на котором пишет источник (pt-BR, en…)


class ArticleTranslation(BaseModel):
    title: str
    lead: str | None


class ArticleInEvent(BaseModel):
    id: uuid.UUID
    title: str
    url: str
    lead: str | None
    published_at: datetime | None
    discovered_at: datetime
    source: ArticleSource | None
    is_duplicate: bool
    attach_method: str
    manual: bool
    relevance: str | None
    clickbait: bool
    rumor_markers: list[str]
    image_url: str | None
    translation: ArticleTranslation | None = None  # на язык интерфейса


class RelatedEvent(BaseModel):
    id: uuid.UUID
    title: str
    kind: str
    relevance: str
    status: str
    last_article_at: datetime


class DraftBrief(BaseModel):
    id: uuid.UUID
    state: str
    current_version: int
    updated_at: datetime


class EventDetail(EventListItem):
    summary: SummaryOut | None
    relevance_rationale: str
    relevance_reason: str | None
    reliability_factors: list[FactorOut]
    reliability_reason: str | None
    rejection_reason: str | None
    rejection_comment: str | None
    manual_overrides: list[str]
    status_changed_at: datetime
    created_by: uuid.UUID | None
    teams: list[EntityRef]
    players: list[EntityRef]
    other_entities: list[EntityKindRef]
    articles: list[ArticleInEvent] | None = None
    related: list[RelatedEvent] | None = None
    draft: DraftBrief | None = None  # BE-T3.7 через composition root
    conflicts: list[dict[str, Any]] | None = None  # BE-T4.1
    original_language: str | None = None  # язык первой статьи события
    translation_pending: bool = False  # перевод на язык интерфейса ещё идёт — UI опрашивает


class SkippedUrl(BaseModel):
    url: str
    event_id: uuid.UUID


class ManualEventCreated(EventDetail):
    skipped_urls: list[SkippedUrl] = []


class MergeRequest(BaseModel):
    other_event_id: uuid.UUID


class MoveRequest(BaseModel):
    target_event_id: uuid.UUID | None = None


class MoveResult(BaseModel):
    source: EventDetail
    target_event_id: uuid.UUID


class AssessmentOverride(BaseModel):
    level: str | None
    reason: str | None = Field(default=None, max_length=500)
