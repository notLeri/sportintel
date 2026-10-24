from enum import StrEnum


class EntityKind(StrEnum):
    COMPETITION = "competition"
    TEAM = "team"
    PLAYER = "player"
    COACH = "coach"
    PERSON = "person"
    VENUE = "venue"


class EntityReviewState(StrEnum):
    APPROVED = "approved"
    PENDING = "pending"
    IGNORED = "ignored"
