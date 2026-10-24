"""Агрегат Event (BE-T2.10). Чистый Python: инварианты, оценки, переходы, ручные правки."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final

from sportintel.modules.events.domain.actor import Actor
from sportintel.modules.events.domain.errors import (
    ArticleNotInEvent,
    CommentRequired,
    InvalidTransition,
    OverrideReasonRequired,
    ReasonRequired,
)
from sportintel.modules.events.domain.policies.workflow import WorkflowPolicy
from sportintel.modules.events.domain.values import (
    ArticleLink,
    AssessmentOrigin,
    EventOrigin,
    EventStatus,
    OverrideField,
    RejectionReason,
    Relevance,
    RelevanceAssessment,
    Reliability,
    ReliabilityAssessment,
    ReliabilityFactor,
    ReliabilityFactorItem,
    TextOrigin,
)
from sportintel.platform.errors import FieldError, ValidationFailed


class _Unset:
    def __repr__(self) -> str:
        return "UNSET"


UNSET: Final = _Unset()
TITLE_MAX, SUMMARY_MAX, COMMENT_MAX = 300, 3000, 500


@dataclass
class ComputedState:
    """Результат refresh_event: применяется только к полям без ручного override."""

    title: str | None = None
    title_origin: TextOrigin | None = None
    summary: str | None = None
    summary_origin: TextOrigin | None = None
    sport_id: str | None = None
    region: str | None = None
    competition_id: uuid.UUID | None = None
    entities: list[tuple[uuid.UUID, str]] = field(default_factory=list)
    entity_mentions: dict[uuid.UUID, int] = field(default_factory=dict)
    relevance: RelevanceAssessment | None = None
    reliability: ReliabilityAssessment | None = None
    article_count: int = 0
    source_count: int = 0
    independent_source_count: int = 0
    source_ids: list[uuid.UUID] = field(default_factory=list)
    centroid: list[float] | None = None
    search_doc: str = ""
    last_article_at: datetime | None = None
    occurred_at: datetime | None = None
    has_clickbait: bool = False
    has_open_conflicts: bool = False
    stale_suspected: bool = False


def _title(value: str) -> str:
    t = " ".join(value.split())
    if not 1 <= len(t) <= TITLE_MAX:
        raise ValidationFailed(details=[FieldError("title", "length", f"1–{TITLE_MAX} characters")])
    return t


@dataclass
class Event:
    id: uuid.UUID
    title: str
    title_origin: TextOrigin
    occurred_at: datetime
    first_seen_at: datetime
    last_article_at: datetime
    status: EventStatus = EventStatus.NEW
    status_changed_at: datetime | None = None
    summary: str | None = None
    summary_origin: TextOrigin | None = None
    sport_id: str | None = None
    region: str | None = None  # страна источников (ISO 3166-1); события не смешивают регионы
    competition_id: uuid.UUID | None = None
    relevance: RelevanceAssessment = field(
        default_factory=lambda: RelevanceAssessment(Relevance.LOW, "", AssessmentOrigin.RULE)
    )
    reliability: ReliabilityAssessment = field(
        default_factory=lambda: ReliabilityAssessment(
            Reliability.UNKNOWN, (), AssessmentOrigin.RULE
        )
    )
    rejection_reason: RejectionReason | None = None
    rejection_comment: str | None = None
    assignee_id: uuid.UUID | None = None
    manual_overrides: set[OverrideField] = field(default_factory=set)
    has_updates_since_edit: bool = False
    has_open_conflicts: bool = False
    stale_suspected: bool = False
    has_clickbait: bool = False
    article_count: int = 0
    source_count: int = 0
    independent_source_count: int = 0
    centroid: list[float] | None = None
    source_ids: list[uuid.UUID] = field(default_factory=list)
    entities: list[tuple[uuid.UUID, str]] = field(default_factory=list)
    origin: EventOrigin = EventOrigin.AUTO
    created_by: uuid.UUID | None = None
    refresh_requested_at: datetime | None = None
    search_doc: str = ""
    version: int = 1
    links: list[ArticleLink] = field(default_factory=list)
    draft_state: str | None = None  # generating|ready|failed — пишет editorial (BE-T3.7)
    draft_last_human_author_id: uuid.UUID | None = None

    # --- создание ---

    @classmethod
    def create_auto(
        cls,
        id: uuid.UUID,
        first: ArticleLink,
        title: str,
        title_origin: TextOrigin,
        occurred_at: datetime,
        now: datetime,
    ) -> "Event":
        e = cls(
            id=id,
            title=_title(title),
            title_origin=title_origin,
            occurred_at=occurred_at,
            first_seen_at=now,
            last_article_at=now,
            status_changed_at=now,
        )
        e.attach(first, now)
        return e

    @classmethod
    def create_manual(
        cls,
        id: uuid.UUID,
        title: str,
        summary: str | None,
        sport_id: str | None,
        competition_id: uuid.UUID | None,
        actor: Actor,
        now: datetime,
    ) -> "Event":
        e = cls(
            id=id,
            title=_title(title),
            title_origin=TextOrigin.HUMAN,
            occurred_at=now,
            first_seen_at=now,
            last_article_at=now,
            status_changed_at=now,
            sport_id=sport_id,
            competition_id=competition_id,
            origin=EventOrigin.MANUAL,
            created_by=actor.id,
        )
        overrides = {OverrideField.TITLE}
        if summary:
            e.summary, e.summary_origin = summary[:SUMMARY_MAX], TextOrigin.HUMAN
            overrides.add(OverrideField.SUMMARY)
        if sport_id:
            overrides.add(OverrideField.SPORT)
        if competition_id:
            overrides.add(OverrideField.COMPETITION)
        e.manual_overrides = overrides
        return e

    # --- статьи ---

    def attach(self, link: ArticleLink, now: datetime) -> None:
        if any(lk.article_id == link.article_id for lk in self.links):
            raise ValidationFailed(
                details=[FieldError("article_id", "duplicate", "article already attached")]
            )
        self.links.append(link)
        if self.manual_overrides:
            self.has_updates_since_edit = True
        self.refresh_requested_at = now

    def detach(self, article_id: uuid.UUID, now: datetime) -> ArticleLink:
        for i, lk in enumerate(self.links):
            if lk.article_id == article_id:
                self.refresh_requested_at = now
                return self.links.pop(i)
        raise ArticleNotInEvent(f"article {article_id} is not in event {self.id}")

    # --- workflow ---

    def transition(
        self,
        to: EventStatus,
        actor: Actor,
        now: datetime,
        *,
        reason: RejectionReason | None = None,
        comment: str | None = None,
        draft_ready: bool = False,
        last_draft_author_id: uuid.UUID | None = None,
        require_second_reviewer: bool = False,
    ) -> None:
        WorkflowPolicy.check(
            self.status,
            to,
            actor,
            draft_ready=draft_ready,
            last_draft_author_id=last_draft_author_id,
            require_second_reviewer=require_second_reviewer,
        )
        if to == EventStatus.REJECTED:
            if reason is None:
                raise ReasonRequired()
            text = (comment or "").strip()
            if reason == RejectionReason.OTHER and not text:
                raise CommentRequired()
            if len(text) > COMMENT_MAX:
                raise CommentRequired(
                    details=[FieldError("comment", "length", f"≤ {COMMENT_MAX} characters")]
                )
            self.rejection_reason, self.rejection_comment = reason, text or None
        if self.status == EventStatus.REJECTED and to == EventStatus.NEW:
            self.rejection_reason = self.rejection_comment = None
        if to == EventStatus.REVIEWING:
            self.assignee_id = actor.id
        if self.status == EventStatus.REVIEWING and to == EventStatus.NEW:
            self.assignee_id = None
        self.status, self.status_changed_at = to, now

    # --- ручные правки ---

    def edit(
        self,
        actor: Actor,
        now: datetime,
        *,
        title: Any = UNSET,
        summary: Any = UNSET,
        sport_id: Any = UNSET,
        competition_id: Any = UNSET,
    ) -> set[OverrideField]:
        changed: set[OverrideField] = set()
        if title is not UNSET and _title(title) != self.title:
            self.title, self.title_origin = _title(title), TextOrigin.HUMAN
            changed.add(OverrideField.TITLE)
        if summary is not UNSET and summary != self.summary:
            if summary is not None and len(summary) > SUMMARY_MAX:
                raise ValidationFailed(
                    details=[FieldError("summary", "length", f"≤ {SUMMARY_MAX} characters")]
                )
            self.summary, self.summary_origin = summary, TextOrigin.HUMAN
            self.has_updates_since_edit = False
            changed.add(OverrideField.SUMMARY)
        if sport_id is not UNSET and sport_id != self.sport_id:
            self.sport_id = sport_id
            changed.add(OverrideField.SPORT)
        if competition_id is not UNSET and competition_id != self.competition_id:
            self.competition_id = competition_id
            changed.add(OverrideField.COMPETITION)
        self.manual_overrides |= changed
        return changed

    def set_entities_manual(
        self, actor: Actor, entity_roles: list[tuple[uuid.UUID, str]], now: datetime
    ) -> None:
        self.entities = list(entity_roles)
        self.manual_overrides.add(OverrideField.ENTITIES)

    @staticmethod
    def _reason(reason: str | None) -> str:
        r = (reason or "").strip()
        if not 3 <= len(r) <= 500:
            raise OverrideReasonRequired()
        return r

    def override_relevance(
        self, level: Relevance, reason: str, actor: Actor, now: datetime
    ) -> None:
        self.relevance = RelevanceAssessment(
            level, self.relevance.rationale, AssessmentOrigin.HUMAN, self._reason(reason)
        )
        self.manual_overrides.add(OverrideField.RELEVANCE)

    def override_reliability(
        self, level: Reliability, reason: str, actor: Actor, now: datetime
    ) -> None:
        self.reliability = ReliabilityAssessment(
            level,
            (ReliabilityFactorItem(ReliabilityFactor.HUMAN_OVERRIDE),),
            AssessmentOrigin.HUMAN,
            self._reason(reason),
        )
        self.manual_overrides.add(OverrideField.RELIABILITY)

    def clear_override(self, f: OverrideField, now: datetime) -> None:
        self.manual_overrides.discard(f)
        self.refresh_requested_at = now

    def apply_computed(self, c: ComputedState, now: datetime) -> None:
        o = self.manual_overrides
        if c.title and OverrideField.TITLE not in o:
            self.title, self.title_origin = _title(c.title), c.title_origin or TextOrigin.SOURCE
        if c.summary is not None and OverrideField.SUMMARY not in o:
            self.summary, self.summary_origin = c.summary, c.summary_origin
        if OverrideField.SPORT not in o:
            self.sport_id = c.sport_id
        if c.region:
            self.region = c.region
        if OverrideField.COMPETITION not in o:
            self.competition_id = c.competition_id
        if OverrideField.ENTITIES not in o:
            self.entities = list(c.entities)
        if c.relevance and OverrideField.RELEVANCE not in o:
            self.relevance = c.relevance
        if c.reliability and OverrideField.RELIABILITY not in o:
            self.reliability = c.reliability
        self.article_count, self.source_count = c.article_count, c.source_count
        self.independent_source_count, self.source_ids = (
            c.independent_source_count,
            list(c.source_ids),
        )
        self.centroid, self.search_doc = c.centroid, c.search_doc
        self.has_clickbait, self.has_open_conflicts, self.stale_suspected = (
            c.has_clickbait,
            c.has_open_conflicts,
            c.stale_suspected,
        )
        if c.last_article_at:
            self.last_article_at = c.last_article_at
        if c.occurred_at:
            self.occurred_at = c.occurred_at
        self.refresh_requested_at = None


__all__ = ["UNSET", "ComputedState", "Event", "InvalidTransition"]
