from enum import StrEnum


class DraftState(StrEnum):
    GENERATING = "generating"
    READY = "ready"
    FAILED = "failed"


class DisclaimerKind(StrEnum):
    UNCONFIRMED = "unconfirmed"
    CONFLICTING = "conflicting"


class VersionOrigin(StrEnum):
    AI = "ai"
    HUMAN = "human"
    TEMPLATE = "template"
