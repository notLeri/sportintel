import uuid
from datetime import UTC, datetime

import pytest

from sportintel.platform.errors import ValidationFailed
from sportintel.platform.pagination import decode_cursor, encode_cursor, split_multi


def test_roundtrip_types() -> None:
    values = (datetime(2026, 10, 8, 12, 30, tzinfo=UTC), uuid.UUID(int=7), 0.0607927, None)
    assert decode_cursor(encode_cursor(values), [datetime, uuid.UUID, float, str]) == values


@pytest.mark.parametrize(
    "bad", ["", "!!!", encode_cursor(("x",)), encode_cursor(("not-a-date", "u"))]
)
def test_invalid_cursor(bad: str) -> None:
    with pytest.raises(ValidationFailed):
        decode_cursor(bad, [datetime, uuid.UUID])


def test_split_multi() -> None:
    assert split_multi(["a,b", "c", " ,d "]) == ["a", "b", "c", "d"]
    assert split_multi(None) == []
