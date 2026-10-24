import uuid
from datetime import UTC, datetime, timedelta

import pytest

from sportintel.modules.events.domain.actor import Actor
from sportintel.modules.events.domain.errors import (
    CommentRequired,
    InvalidTransition,
    OverrideReasonRequired,
    ReasonRequired,
    TransitionForbidden,
)
from sportintel.modules.events.domain.event import ComputedState, Event
from sportintel.modules.events.domain.values import (
    ArticleLink,
    AssessmentOrigin,
    AttachMethod,
    OverrideField,
    RejectionReason,
    Relevance,
    RelevanceAssessment,
    Role,
    TextOrigin,
)
from sportintel.modules.events.domain.values import (
    EventStatus as S,
)
from sportintel.platform.errors import ValidationFailed

NOW = datetime(2026, 10, 8, 12, tzinfo=UTC)
ED = Actor(uuid.uuid4(), Role.EDITOR)
RS = Actor(uuid.uuid4(), Role.RESEARCHER)


def link(n: int = 1) -> ArticleLink:
    return ArticleLink(uuid.UUID(int=n), NOW, 0.9, AttachMethod.NEW)


def event() -> Event:
    return Event.create_auto(uuid.uuid4(), link(), "Flamengo vence", TextOrigin.SOURCE, NOW, NOW)


def test_reject_rules() -> None:
    e = event()
    with pytest.raises(ReasonRequired):
        e.transition(S.REJECTED, RS, NOW)
    with pytest.raises(CommentRequired):
        e.transition(S.REJECTED, RS, NOW, reason=RejectionReason.OTHER)
    with pytest.raises(CommentRequired):
        e.transition(S.REJECTED, RS, NOW, reason=RejectionReason.OTHER, comment="x" * 501)
    e.transition(S.REJECTED, RS, NOW, reason=RejectionReason.OTHER, comment="fora do escopo")
    assert (e.status, e.rejection_reason, e.rejection_comment) == (
        S.REJECTED,
        RejectionReason.OTHER,
        "fora do escopo",
    )
    e.transition(S.NEW, ED, NOW + timedelta(minutes=1))
    assert (e.rejection_reason, e.rejection_comment, e.status_changed_at) == (
        None,
        None,
        NOW + timedelta(minutes=1),
    )


def test_assignee_and_draft_ready() -> None:
    e = event()
    e.transition(S.REVIEWING, RS, NOW)
    assert e.assignee_id == RS.id
    e.transition(S.NEW, RS, NOW)
    assert e.assignee_id is None
    e.transition(S.SELECTED, RS, NOW)
    e.transition(S.DRAFT, RS, NOW)
    with pytest.raises(InvalidTransition):
        e.transition(S.READY, ED, NOW, draft_ready=False)
    with pytest.raises(TransitionForbidden):
        e.transition(
            S.READY,
            ED,
            NOW,
            draft_ready=True,
            last_draft_author_id=ED.id,
            require_second_reviewer=True,
        )
    e.transition(
        S.READY, ED, NOW, draft_ready=True, last_draft_author_id=RS.id, require_second_reviewer=True
    )
    assert e.status == S.READY


def test_attach_duplicate_and_updates_since_edit() -> None:
    e = event()
    with pytest.raises(ValidationFailed):
        e.attach(link(1), NOW)
    e.edit(ED, NOW, title="Flamengo vence o clássico")
    e.attach(link(2), NOW)
    assert e.has_updates_since_edit
    assert e.refresh_requested_at == NOW


def test_edit_overrides_and_apply_computed_respects_them() -> None:
    e = event()
    assert e.edit(ED, NOW) == set()
    changed = e.edit(ED, NOW, title="Título editado", summary="Resumo humano")
    assert changed == {OverrideField.TITLE, OverrideField.SUMMARY}
    assert (e.title_origin, e.summary_origin) == (TextOrigin.HUMAN, TextOrigin.HUMAN)
    e.apply_computed(
        ComputedState(
            title="Do sistema",
            summary="Do sistema",
            sport_id="football",
            article_count=3,
            source_count=2,
            relevance=RelevanceAssessment(Relevance.HIGH, "r", AssessmentOrigin.RULE),
        ),
        NOW,
    )
    assert (e.title, e.summary, e.sport_id, e.article_count, e.relevance.level) == (
        "Título editado",
        "Resumo humano",
        "football",
        3,
        Relevance.HIGH,
    )


def test_override_reason_and_clear() -> None:
    e = event()
    with pytest.raises(OverrideReasonRequired):
        e.override_relevance(Relevance.HIGH, "no", ED, NOW)
    e.override_relevance(Relevance.HIGH, "decisão editorial", ED, NOW)
    e.apply_computed(
        ComputedState(relevance=RelevanceAssessment(Relevance.LOW, "r", AssessmentOrigin.RULE)), NOW
    )
    assert (e.relevance.level, e.relevance.origin) == (Relevance.HIGH, AssessmentOrigin.HUMAN)
    e.clear_override(OverrideField.RELEVANCE, NOW)
    e.apply_computed(
        ComputedState(relevance=RelevanceAssessment(Relevance.LOW, "r", AssessmentOrigin.RULE)), NOW
    )
    assert e.relevance.level == Relevance.LOW


def test_manual_event_and_detach() -> None:
    e = Event.create_manual(uuid.uuid4(), "Evento manual", "Resumo", "football", None, ED, NOW)
    assert e.manual_overrides == {OverrideField.TITLE, OverrideField.SUMMARY, OverrideField.SPORT}
    from sportintel.modules.events.domain.errors import ArticleNotInEvent

    with pytest.raises(ArticleNotInEvent):
        e.detach(uuid.UUID(int=99), NOW)
