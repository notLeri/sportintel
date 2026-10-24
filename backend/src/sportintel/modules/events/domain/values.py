import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class Role(StrEnum):  # значения = identity.Role; домен не импортирует другие модули
    RESEARCHER = "researcher"
    EDITOR = "editor"
    ADMIN = "admin"


ROLE_RANK = {Role.RESEARCHER: 1, Role.EDITOR: 2, Role.ADMIN: 3}


class EventStatus(StrEnum):
    NEW = "NEW"
    REVIEWING = "REVIEWING"
    SELECTED = "SELECTED"
    DRAFT = "DRAFT"
    READY = "READY"
    PUBLISHED = "PUBLISHED"
    REJECTED = "REJECTED"


class Relevance(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    IRRELEVANT = "IRRELEVANT"


RELEVANCE_RANK = {Relevance.HIGH: 3, Relevance.MEDIUM: 2, Relevance.LOW: 1, Relevance.IRRELEVANT: 0}


class Reliability(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class AssessmentOrigin(StrEnum):
    AI = "ai"
    RULE = "rule"
    HUMAN = "human"


class TextOrigin(StrEnum):
    AI = "ai"
    HUMAN = "human"
    SOURCE = "source"
    TEMPLATE = "template"


class EventOrigin(StrEnum):
    AUTO = "auto"
    MANUAL = "manual"


class RejectionReason(StrEnum):
    DUPLICATE = "DUPLICATE"
    IRRELEVANT = "IRRELEVANT"
    LOW_QUALITY = "LOW_QUALITY"
    INCORRECT = "INCORRECT"
    OLD_NEWS = "OLD_NEWS"
    NOT_TELEGRAM_WORTHY = "NOT_TELEGRAM_WORTHY"
    OTHER = "OTHER"


class AttachMethod(StrEnum):
    NEW = "new"
    AUTO = "auto"
    ADJUDICATED = "adjudicated"
    SYNDICATION = "syndication"
    MANUAL = "manual"


class RelationKind(StrEnum):
    RELATED = "related"
    FOLLOW_UP = "follow_up"
    POSSIBLE_DUPLICATE = "possible_duplicate"
    OLD_NEWS = "old_news"


class ReliabilityFactor(StrEnum):
    OFFICIAL_CONFIRMED = "official_confirmed"
    INDEPENDENT_TIER_A_2PLUS = "independent_tier_a_2plus"
    SINGLE_TIER_A = "single_tier_a"
    INDEPENDENT_TIER_B_2PLUS = "independent_tier_b_2plus"
    TIER_C_ONLY = "tier_c_only"
    RUMOR_MARKERS = "rumor_markers"
    CLICKBAIT = "clickbait"
    OPEN_CONFLICT_CAP = "open_conflict_cap"
    SINGLE_SOURCE = "single_source"
    UNKNOWN_TIER = "unknown_tier"
    UNTRUSTED_ONLY = "untrusted_only"
    NO_ARTICLES = "no_articles"
    HUMAN_OVERRIDE = "human_override"


class OverrideField(StrEnum):
    TITLE = "title"
    SUMMARY = "summary"
    SPORT = "sport"
    COMPETITION = "competition"
    ENTITIES = "entities"
    RELEVANCE = "relevance"
    RELIABILITY = "reliability"


@dataclass(frozen=True)
class RelevanceAssessment:
    level: Relevance
    rationale: str
    origin: AssessmentOrigin
    reason: str | None = None


@dataclass(frozen=True)
class ReliabilityFactorItem:
    code: ReliabilityFactor
    detail: str = ""


@dataclass(frozen=True)
class ReliabilityAssessment:
    level: Reliability
    factors: tuple[ReliabilityFactorItem, ...]
    origin: AssessmentOrigin
    reason: str | None = None


@dataclass(frozen=True)
class ArticleLink:
    article_id: uuid.UUID
    attached_at: datetime
    score: float | None
    method: AttachMethod
    cluster_locked: bool = False
    is_duplicate: bool = False
