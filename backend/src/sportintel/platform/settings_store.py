"""Runtime-настройки `platform.app_settings` (CONV §3). Default — в схеме; кэш процесса 60 с."""

import json
import re
import time
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator
from sqlalchemy import text

from sportintel.platform.db import Database, UnitOfWork
from sportintel.platform.errors import FieldError, NotFound, ValidationFailed

CACHE_TTL_S = 60.0
Level = Literal["HIGH", "MEDIUM", "LOW"]
Lang = Literal["pt-BR", "en", "ru"]


class UnknownSettingsKey(NotFound):
    code = "settings.unknown_key"
    title = "Unknown settings key"


class InvalidSettingsValue(ValidationFailed):
    code = "settings.invalid_value"
    title = "Invalid settings value"


class RelevanceRubric(BaseModel):
    text: str = Field(default="", max_length=8000)  # seed — BE-T2.7 (только шаг llm)


_CYRILLIC = re.compile(r"[а-яё]", re.IGNORECASE)


def by_language(words: list[str], latin: str = "pt-BR") -> dict[str, list[str]]:
    """Прежний плоский список слов → по языкам источников: кириллица — ru, остальное — latin."""
    out: dict[str, list[str]] = {}
    for w in words:
        out.setdefault("ru" if _CYRILLIC.search(w) else latin, []).append(w)
    return out


class RelevanceRule(BaseModel):
    """Сигнал важности. Название — на языке интерфейса; слова — на языках источников:
    они ищутся в текстах статей, поэтому португальские статьи ловятся только португальскими словами."""

    name: str
    weight: int
    words: dict[Lang, list[str]] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _legacy_keywords(cls, v: Any) -> Any:
        if isinstance(v, dict) and "keywords" in v:
            v = {**v, "words": v.get("words") or by_language(v["keywords"])}
            v.pop("keywords")
        return v

    @property
    def all_words(self) -> list[str]:
        return [w for ws in self.words.values() for w in ws]


class LevelThresholds(BaseModel):
    HIGH: int = 6
    MEDIUM: int = 3
    LOW: int = 1


class EnrichRules(BaseModel):
    """Правила обогащения без LM (ADR-004, BE-T2.7). Seed-значения — в intelligence."""

    sport_url_patterns: dict[str, list[str]] = Field(default_factory=dict)
    sport_keywords: dict[str, list[str]] = Field(default_factory=dict)
    # Имена-омонимы (город, обычное слово): сами по себе вид спорта не определяют.
    ambiguous_entities: list[str] = Field(default_factory=list)
    # Полностью спортивные сайты: материал всегда спортивный, омонимы считаются надёжными.
    sports_domains: list[str] = Field(default_factory=list)
    rss_category_map: dict[str, str] = Field(default_factory=dict)
    relevance_rules: list[RelevanceRule] = Field(default_factory=list)
    competition_weight: dict[str, int] = Field(default_factory=dict)
    level_thresholds: LevelThresholds = Field(default_factory=LevelThresholds)
    # Вес совпадения в тексте статьи относительно заголовка (×2). Пороги откалиброваны на заголовках.
    body_weight: float = Field(default=1.0, ge=0, le=2)
    top_team_bonus: int = Field(default=1, ge=0, le=10)  # клуб высшего приоритета в материале
    rumor_penalty: int = Field(default=1, ge=0, le=10)  # маркеры слуха
    clickbait_penalty: int = Field(default=2, ge=0, le=10)  # кликбейтный заголовок
    rumor_markers: dict[Lang, list[str]] = Field(default_factory=dict)  # на языках источников
    clickbait_patterns: list[str] = Field(default_factory=list)
    version: int = 1

    @field_validator("rumor_markers", mode="before")
    @classmethod
    def _legacy_markers(cls, v: Any) -> Any:
        return by_language(v) if isinstance(v, list) else v

    @property
    def all_rumor_markers(self) -> list[str]:
        return [w for ws in self.rumor_markers.values() for w in ws]


class Languages(BaseModel):
    ui_language: Literal["ru", "en"] = "ru"  # язык интерфейса и перевода событий — для всех
    analysis_language: Lang = "pt-BR"
    telegram_language: Lang = "en"
    # фоновый перевод событий — от этой важности (каждое событие — несколько вызовов модели)
    translate_min_relevance: Level = "MEDIUM"


class AiRouting(BaseModel):
    enrich_article: Literal["rules", "llm"] = "rules"
    cluster_adjudicate: Literal["rules", "llm"] = "rules"
    event_summary: Literal["rules", "llm"] = "rules"
    telegram_draft: Literal["template", "llm"] = "template"
    conflict_check: Literal["off", "llm"] = "off"
    embeddings: Literal["off", "on"] = "off"
    llm_model: str = "qwen3:14b"
    translation_model: str = "gemma3:12b"  # прогон 2026-10-10: лучший русский среди локальных
    embedding_model: str = "bge-m3"
    escalation_model: str | None = None


class AiCircuitBreaker(BaseModel):
    error_rate: float = 0.2
    window_minutes: int = 10
    min_calls: int = 10
    pause_minutes: int = 5


class Clustering(BaseModel):
    window_hours: int = 72
    top_k: int = 20
    w_cos: float = 0.6
    w_entities: float = 0.3
    w_competition: float = 0.1
    w_lex: float = 0.5
    lex_min: float = 0.2  # ADR-003 (лексический режим)
    claim_conflict_penalty: float = 0.15
    t_high: float = 0.58  # ADR-003; при включении эмбеддингов — перекалибровать
    t_low: float = 0.38
    adjudication_enabled: bool = True
    stale_window_days: int = 30
    stale_similarity: float = 0.88

    @model_validator(mode="after")
    def _check(self) -> "Clustering":
        weights = (self.w_cos, self.w_entities, self.w_competition, self.w_lex)
        if not 0 <= self.t_low < self.t_high <= 1 or min(weights) < 0 or sum(weights) <= 0:
            raise ValueError(
                "need 0 <= t_low < t_high <= 1 and non-negative weights with positive sum"
            )
        return self


class EntityLinking(BaseModel):
    trigram_threshold: float = 0.45
    auto_create_players: bool = True


class Summary(BaseModel):
    min_relevance: Level = "MEDIUM"
    debounce_minutes: int = 10
    max_evidence_fragments: int = 12


class Content(BaseModel):
    max_text_chars_for_ai: int = 12000
    lead_max_chars: int = 500


class HealthWatch(BaseModel):
    queue_age_minutes: int = 15
    ingest_lag_p95_minutes: int = 15
    silent_source_hours: int = 6
    active_hours_start: int = 8
    active_hours_end: int = 23
    fetch_fail_streak: int = 5
    ai_error_rate: float = 0.2
    repeat_minutes: int = 60


class Briefs(BaseModel):
    auto_min_relevance: Level = "HIGH"
    # Пусто — брифы только по кнопке. Локальная модель: ~50 с на бриф, 100 событий ≈ 1,5 ч на язык.
    auto_languages: list[Lang] = Field(default_factory=list)
    max_age_hours: int = Field(default=24, ge=1, le=168)


class Drafts(BaseModel):
    """Формат всех постов: что включать и образец, по которому пишет ИИ."""

    post_example: str = Field(default="", max_length=4000)  # Telegram HTML
    post_instructions: str = Field(default="", max_length=1000)
    inline_links: bool = True  # ИИ ставит ссылки на источники прямо в тексте
    include_emoji: bool = True
    include_source_link: bool = True
    max_hashtags: int = Field(default=4, ge=0, le=10)  # 0 — без хэштегов
    auto_min_relevance: Level = "MEDIUM"
    auto_mode: Literal["template", "llm"] = "llm"  # первый вариант поста пишет ИИ (если подключён)
    sport_emoji: dict[str, str] = Field(
        default_factory=lambda: {
            "football": "⚽",
            "basketball": "🏀",
            "tennis": "🎾",
            "mma": "🥊",
            "formula1": "🏎️",
            "volleyball": "🏐",
            "hockey": "🏒",
            "igaming": "🎰",
            "holidays": "📅",
        }
    )
    template_also_reported: bool = True

    @property
    def emojis(self) -> dict[str, str]:
        return self.sport_emoji if self.include_emoji else {}


SETTINGS_SCHEMAS: dict[str, type[BaseModel]] = {
    "relevance_rubric": RelevanceRubric,
    "enrich_rules": EnrichRules,
    "languages": Languages,
    "ai_routing": AiRouting,
    "ai_circuit_breaker": AiCircuitBreaker,
    "clustering": Clustering,
    "entity_linking": EntityLinking,
    "summary": Summary,
    "content": Content,
    "health_watch": HealthWatch,
    "drafts": Drafts,
    "briefs": Briefs,
}
# Значения по умолчанию, которые подставляют модули-владельцы (например, seed правил в intelligence).
DEFAULT_OVERRIDES: dict[str, dict[str, Any]] = {}

_cache: dict[str, tuple[float, BaseModel]] = {}


def schema_for(key: str) -> type[BaseModel]:
    try:
        return SETTINGS_SCHEMAS[key]
    except KeyError:
        raise UnknownSettingsKey(f"unknown settings key {key!r}") from None


def clear_cache() -> None:
    _cache.clear()


async def get(db: Database, key: str) -> Any:
    """Экземпляр схемы ключа; если строки нет — default схемы."""
    schema = schema_for(key)
    hit = _cache.get(key)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    async with db.uow() as uow:
        value = await _load(uow, key)
    model = schema.model_validate({**DEFAULT_OVERRIDES.get(key, {}), **(value or {})})
    _cache[key] = (time.monotonic() + CACHE_TTL_S, model)
    return model


async def _load(uow: UnitOfWork, key: str) -> dict[str, Any] | None:
    row = await uow.session.execute(
        text("SELECT value FROM platform.app_settings WHERE key = :k"), {"k": key}
    )
    return row.scalar()


async def put(
    uow: UnitOfWork, key: str, value: dict[str, Any], actor_id: uuid.UUID | None, now: datetime
) -> BaseModel:
    schema = schema_for(key)
    try:
        model = schema.model_validate(value)
    except ValidationError as e:
        raise InvalidSettingsValue(
            details=[
                FieldError(".".join(str(p) for p in err["loc"]), err["type"], err["msg"])
                for err in e.errors()
            ]
        ) from None
    await uow.session.execute(
        text(
            "INSERT INTO platform.app_settings (key, value, updated_by, updated_at) VALUES (:k, CAST(:v AS jsonb), :u, :t)"
            " ON CONFLICT (key) DO UPDATE SET value = excluded.value, updated_by = excluded.updated_by, updated_at = excluded.updated_at"
        ),
        {"k": key, "v": json.dumps(model.model_dump(mode="json")), "u": actor_id, "t": now},
    )
    _cache.pop(key, None)
    return model


async def get_raw(uow: UnitOfWork, key: str) -> dict[str, Any] | None:
    schema_for(key)
    return await _load(uow, key)


async def get_row(uow: UnitOfWork, key: str) -> dict[str, Any] | None:
    """Строка настройки с метаданными (BE-T4.10)."""
    schema_for(key)
    row = (
        await uow.session.execute(
            text("SELECT value, updated_by, updated_at FROM platform.app_settings WHERE key = :k"),
            {"k": key},
        )
    ).first()
    return dict(row._mapping) if row else None


def default_value(key: str) -> dict[str, Any]:
    return schema_for(key).model_validate(DEFAULT_OVERRIDES.get(key, {})).model_dump(mode="json")


async def ui_language(uow: UnitOfWork) -> str:
    """Язык интерфейса редакции (languages.ui_language) — в той же транзакции."""
    raw = await get_raw(uow, "languages") or {}
    return str(raw.get("ui_language") or Languages().ui_language)
