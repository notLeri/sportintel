import uuid
from datetime import UTC, datetime

from sportintel.modules.audit.domain.diff import TRUNCATED, clip, diff


def test_only_changed_keys_nested_whole_and_serialized() -> None:
    i = uuid.UUID(int=1)
    at = datetime(2026, 10, 9, tzinfo=UTC)
    before, after = diff(
        {"title": "a", "tags": ["x"], "meta": {"k": 1}, "same": 1, "at": at},
        {"title": "b", "tags": ["x"], "meta": {"k": 2}, "same": 1, "at": at, "owner": i},
    )
    assert before == {"title": "a", "meta": {"k": 1}, "owner": None}
    assert after == {"title": "b", "meta": {"k": 2}, "owner": str(i)}


def test_clip_only_when_large() -> None:
    small = {"body": "x" * 3000}
    assert clip(small) == small
    big = {"body": "y" * 70_000, "n": 1}
    got = clip(big)
    assert got["body"].endswith(TRUNCATED)
    assert len(got["body"]) == 2000 + len(TRUNCATED)
