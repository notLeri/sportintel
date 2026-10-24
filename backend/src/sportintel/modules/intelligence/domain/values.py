from enum import StrEnum


class Relevance(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    IRRELEVANT = "IRRELEVANT"


class ClaimAttribute(StrEnum):
    AVAILABILITY = "availability"
    INJURY = "injury"
    TRANSFER = "transfer"
    SCORE = "score"
    LINEUP = "lineup"
    SUSPENSION = "suspension"
    COACH_CHANGE = "coach_change"
    CONTRACT = "contract"
    SCHEDULE = "schedule"
    OTHER = "other"


class ClaimModality(StrEnum):
    CONFIRMED = "confirmed"
    EXPECTED = "expected"
    RUMOR = "rumor"
    DENIED = "denied"
