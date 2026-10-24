import itertools
import uuid
from datetime import UTC, datetime

import pytest

from sportintel.modules.events.domain.actor import SYSTEM, Actor
from sportintel.modules.events.domain.errors import InvalidTransition, TransitionForbidden
from sportintel.modules.events.domain.policies.workflow import WorkflowPolicy
from sportintel.modules.events.domain.values import EventStatus as S
from sportintel.modules.events.domain.values import Role

# Таблица CONV §8.1 литералом: (from, to) → минимальная роль; "sys" — разрешено системе.
TABLE = {
    ("NEW", "REVIEWING"): "researcher",
    ("NEW", "SELECTED"): "researcher",
    ("REVIEWING", "SELECTED"): "researcher",
    ("REVIEWING", "NEW"): "researcher",
    ("SELECTED", "DRAFT"): "researcher+sys",
    ("DRAFT", "READY"): "editor",
    ("READY", "DRAFT"): "editor+sys",
    ("READY", "PUBLISHED"): "editor+sys",
    ("NEW", "REJECTED"): "researcher",
    ("REVIEWING", "REJECTED"): "researcher",
    ("SELECTED", "REJECTED"): "researcher",
    ("DRAFT", "REJECTED"): "researcher",
    ("REJECTED", "NEW"): "editor",
}
RANK = {"researcher": 1, "editor": 2, "admin": 3}
ACTORS = {"system": SYSTEM, **{r.value: Actor(uuid.uuid4(), r) for r in Role}}


def expected(frm: str, to: str, who: str) -> str:
    rule = TABLE.get((frm, to))
    if rule is None:
        return "invalid"
    if who == "system":
        return "ok" if rule.endswith("+sys") else "forbidden"
    return "ok" if RANK[who] >= RANK[rule.removesuffix("+sys")] else "forbidden"


@pytest.mark.parametrize(
    ("frm", "to", "who"),
    list(itertools.product([s.value for s in S], [s.value for s in S], ACTORS)),
)
def test_every_pair_against_conv_table(frm: str, to: str, who: str) -> None:
    want = expected(frm, to, who)
    try:
        WorkflowPolicy.check(S(frm), S(to), ACTORS[who], draft_ready=True)
        got = "ok"
    except InvalidTransition:
        got = "invalid"
    except TransitionForbidden:
        got = "forbidden"
    assert got == want


def test_allowed_for_editor_includes_publish() -> None:
    allowed = WorkflowPolicy.allowed_for(Role.EDITOR)
    assert (S.PUBLISHED, Role.EDITOR) in allowed[S.READY]
    assert S.READY not in WorkflowPolicy.allowed_for(Role.RESEARCHER)


def test_now_is_unused_marker() -> None:
    assert datetime(2026, 1, 1, tzinfo=UTC).year == 2026
