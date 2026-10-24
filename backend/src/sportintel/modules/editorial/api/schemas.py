import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

PostLang = Literal["pt-BR", "en", "ru"]


class DraftCreate(BaseModel):
    # brief — версия из AI-брифа на языке lang (бриф должен быть готов); None → ai_routing.telegram_draft
    mode: Literal["template", "llm", "empty", "brief"] | None = None
    lang: PostLang | None = None


class DraftRegenerate(BaseModel):
    mode: Literal["template", "llm", "brief"] | None = None
    lang: PostLang | None = None


class DraftTranslate(BaseModel):
    lang: Literal["ru", "en"]


class DraftSave(BaseModel):
    body_tg_html: str = Field(max_length=20_000)
    image_url: str | None = Field(default=None, max_length=2048, pattern=r"^https://")
    disclaimer_removed: bool = False


class CitationOut(BaseModel):
    n: int
    article_id: uuid.UUID
    source_name: str


class DraftVersionDTO(BaseModel):
    n: int
    lang: str
    body_tg_html: str
    image_url: str | None
    disclaimer_kinds: list[str]
    disclaimer_removed: bool
    disclaimer_text: str | None
    origin: str
    citations: list[CitationOut]
    grounding: dict[str, Any] | None
    author_id: uuid.UUID | None
    created_at: datetime
    plain_length: int
    max_length: int


class VersionBrief(BaseModel):
    n: int
    lang: str
    origin: str
    author_id: uuid.UUID | None
    created_at: datetime


class DraftChannel(BaseModel):
    """Approval channel: publishes the current version after "Ready" if the language matches."""

    name: str
    language: str
    active: bool
    blocked: Literal["language", "filters", "too_old"] | None = None  # почему не уйдёт


class DraftDetail(BaseModel):
    id: uuid.UUID
    event_id: uuid.UUID
    state: str
    failure_code: str | None
    current: DraftVersionDTO | None
    versions: list[VersionBrief]
    version: int
    auto: bool
    channels: list[DraftChannel] = []


class DraftCopied(BaseModel):
    version_n: int = Field(ge=1)
