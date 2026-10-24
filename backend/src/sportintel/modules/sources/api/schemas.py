"""Схемы API источников (BE-T1.2 §8; имена фиксированы — из них генерируются TS-типы)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from sportintel.modules.sources.domain.source import Source
from sportintel.modules.sources.domain.values import (
    ContentPolicy,
    SourceHealth,
    SourceKind,
    SourceTier,
)


class SourceBrief(BaseModel):
    id: uuid.UUID
    name: str
    domain: str
    tier: SourceTier | None
    region: str
    active: bool

    @classmethod
    def of(cls, s: Source) -> "SourceBrief":
        return cls(
            id=s.id, name=s.name, domain=s.domain, tier=s.tier, region=s.region, active=s.active
        )


class SourceAdminItem(SourceBrief):
    kind: SourceKind
    owner_group: str | None
    health: SourceHealth
    last_success_at: datetime | None
    last_new_article_at: datetime | None
    articles_24h: int | None  # BE-T4.8 (через composition): sources не читает статьи
    consecutive_failures: int
    version: int

    @classmethod
    def of(cls, s: Source) -> "SourceAdminItem":
        return cls(
            **SourceBrief.of(s).model_dump(),
            kind=s.kind,
            owner_group=s.owner_group,
            health=s.health,
            last_success_at=s.last_success_at,
            last_new_article_at=s.last_new_article_at,
            articles_24h=None,
            consecutive_failures=s.consecutive_failures,
            version=s.version,
        )


class SourceBriefList(BaseModel):
    items: list[SourceBrief]


class SourceAdminList(BaseModel):
    items: list[SourceAdminItem]


class SourceDetail(BaseModel):
    id: uuid.UUID
    name: str
    domain: str
    base_url: str
    kind: SourceKind
    feed_urls: list[str]
    parser_profile: str
    tier: SourceTier | None
    owner_group: str | None
    language: str
    region: str
    poll_interval_seconds: int
    min_request_gap_ms: int
    content_policy: ContentPolicy
    content_ttl_days: int
    url_keep_params: list[str]
    tos_notes: str
    active: bool
    health: SourceHealth
    consecutive_failures: int
    next_poll_at: datetime | None
    last_success_at: datetime | None
    last_new_article_at: datetime | None
    version: int

    @classmethod
    def of(cls, s: Source) -> "SourceDetail":
        return cls(**{name: getattr(s, name) for name in cls.model_fields})


class SourceCreate(BaseModel):
    name: str = Field(max_length=120)
    base_url: str = Field(max_length=2048)
    kind: SourceKind
    feed_urls: list[str] = Field(default_factory=list, max_length=20)
    tier: SourceTier | None = None
    owner_group: str | None = None
    language: str = "en"
    region: str = Field(default="BR", min_length=2, max_length=2)
    parser_profile: str = "default"
    poll_interval_seconds: int = 300
    min_request_gap_ms: int = 2000
    content_policy: ContentPolicy = ContentPolicy.TRANSIENT_TEXT
    content_ttl_days: int = 7
    url_keep_params: list[str] = Field(default_factory=list, max_length=50)
    tos_notes: str = Field(default="", max_length=4000)
    active: bool = True


class SourceUpdate(BaseModel):
    """PATCH: отсутствующее поле не меняется; null у nullable — сбросить (model_fields_set)."""

    name: str | None = Field(default=None, max_length=120)
    base_url: str | None = Field(default=None, max_length=2048)
    kind: SourceKind | None = None  # неизменяем: присутствие в теле → 422 immutable
    feed_urls: list[str] | None = Field(default=None, max_length=20)
    tier: SourceTier | None = None
    owner_group: str | None = None
    language: str | None = None
    region: str | None = Field(default=None, min_length=2, max_length=2)
    parser_profile: str | None = None
    poll_interval_seconds: int | None = None
    min_request_gap_ms: int | None = None
    content_policy: ContentPolicy | None = None
    content_ttl_days: int | None = None
    url_keep_params: list[str] | None = Field(default=None, max_length=50)
    tos_notes: str | None = Field(default=None, max_length=4000)
    active: bool | None = None


class FetchRunItem(BaseModel):
    id: uuid.UUID
    feed_url: str | None
    started_at: datetime
    finished_at: datetime | None
    status: str
    http_status: int | None
    items_seen: int
    items_new: int
    error_code: str | None
    error_detail: str | None


class FetchRunPage(BaseModel):
    items: list[FetchRunItem]
    next_cursor: str | None
