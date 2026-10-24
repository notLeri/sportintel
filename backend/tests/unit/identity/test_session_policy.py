from datetime import UTC, datetime, timedelta

import pytest

from sportintel.modules.identity.domain.session import SessionPolicy, SessionRecord
from sportintel.modules.identity.domain.user import validate_timezone
from sportintel.platform.errors import ValidationFailed
from sportintel.platform.ids import new_id

T0 = datetime(2026, 10, 7, 12, tzinfo=UTC)
P = SessionPolicy()


def record(**kw: object) -> SessionRecord:
    idle, absolute = P.expiries(T0)
    base = {
        "id_hash": b"h",
        "user_id": new_id(),
        "csrf_token": "c",
        "created_at": T0,
        "last_seen_at": T0,
        "idle_expires_at": idle,
        "absolute_expires_at": absolute,
    }
    return SessionRecord(**{**base, **kw})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("offset", "valid"),
    [(timedelta(hours=11, minutes=59), True), (timedelta(hours=12), False)],
)
def test_idle_boundary(offset: timedelta, valid: bool) -> None:
    assert P.is_valid(record(), T0 + offset) is valid


def test_absolute_boundary_even_if_recently_touched() -> None:
    s = record(idle_expires_at=T0 + timedelta(days=8))
    assert P.is_valid(s, T0 + timedelta(days=7) - timedelta(seconds=1))
    assert not P.is_valid(s, T0 + timedelta(days=7))


@pytest.mark.parametrize(
    ("after", "touch"),
    [(timedelta(minutes=4, seconds=59), False), (timedelta(minutes=5, seconds=1), True)],
)
def test_should_touch(after: timedelta, touch: bool) -> None:
    assert P.should_touch(record(), T0 + after) is touch


def test_touch_never_extends_idle_past_absolute() -> None:
    s = record()
    late = T0 + timedelta(days=6, hours=20)
    touched = P.touched(s, late)
    assert touched.idle_expires_at == s.absolute_expires_at
    assert touched.last_seen_at == late


def test_new_session_expiries() -> None:
    idle, absolute = P.expiries(T0)
    assert (idle - T0, absolute - T0) == (timedelta(hours=12), timedelta(days=7))


def test_timezone_validation() -> None:
    assert validate_timezone("Europe/Moscow") == "Europe/Moscow"
    with pytest.raises(ValidationFailed):
        validate_timezone("Mars/Olympus")
