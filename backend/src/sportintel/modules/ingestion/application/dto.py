from dataclasses import dataclass, field


@dataclass
class FetchSummary:
    feeds: int = 0
    ok: int = 0
    not_modified: int = 0
    errors: int = 0
    items_seen: int = 0
    items_new: int = 0
    skipped: bool = False
    error_codes: list[str] = field(default_factory=list)
