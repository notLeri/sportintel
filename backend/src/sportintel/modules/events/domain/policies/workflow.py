"""State machine события — канон CONV §8.1."""

from collections.abc import Mapping

from sportintel.modules.events.domain.actor import Actor
from sportintel.modules.events.domain.errors import InvalidTransition, TransitionForbidden
from sportintel.modules.events.domain.values import ROLE_RANK, EventStatus, Role

S = EventStatus
R, E = Role.RESEARCHER, Role.EDITOR

ALLOWED: Mapping[tuple[EventStatus, EventStatus], Role] = {
    (S.NEW, S.REVIEWING): R,
    (S.NEW, S.SELECTED): R,
    (S.REVIEWING, S.SELECTED): R,
    (S.REVIEWING, S.NEW): R,
    (S.SELECTED, S.DRAFT): R,
    (S.DRAFT, S.READY): E,
    (S.READY, S.DRAFT): E,
    (S.READY, S.PUBLISHED): E,
    (S.NEW, S.REJECTED): R,
    (S.REVIEWING, S.REJECTED): R,
    (S.SELECTED, S.REJECTED): R,
    (S.DRAFT, S.REJECTED): R,
    (S.REJECTED, S.NEW): E,
}
# READY → PUBLISHED: утверждённый пост отправил бот канала (фаза 6, ADR-05 пересмотрен).
SYSTEM_ALLOWED = frozenset({(S.SELECTED, S.DRAFT), (S.READY, S.DRAFT), (S.READY, S.PUBLISHED)})


class WorkflowPolicy:
    @staticmethod
    def check(
        frm: EventStatus,
        to: EventStatus,
        actor: Actor,
        *,
        draft_ready: bool = False,
        last_draft_author_id: object = None,
        require_second_reviewer: bool = False,
    ) -> None:
        pair = (frm, to)
        if pair not in ALLOWED:
            raise InvalidTransition(f"{frm} → {to} is not allowed")
        if actor.is_system:
            if pair not in SYSTEM_ALLOWED:
                raise TransitionForbidden(f"system cannot do {frm} → {to}")
        elif actor.role is None or ROLE_RANK[actor.role] < ROLE_RANK[ALLOWED[pair]]:
            raise TransitionForbidden(f"{frm} → {to} requires {ALLOWED[pair]}")
        if pair == (S.DRAFT, S.READY):
            if not draft_ready:
                raise InvalidTransition("draft not ready")
            if (
                require_second_reviewer
                and actor.id is not None
                and actor.id == last_draft_author_id
            ):
                raise TransitionForbidden("second reviewer required")

    @staticmethod
    def allowed_for(role: Role) -> dict[EventStatus, list[tuple[EventStatus, Role]]]:
        out: dict[EventStatus, list[tuple[EventStatus, Role]]] = {}
        for (frm, to), min_role in ALLOWED.items():
            if ROLE_RANK[role] >= ROLE_RANK[min_role]:
                out.setdefault(frm, []).append((to, min_role))
        return out
