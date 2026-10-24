import pytest

from sportintel.platform import errors as e


@pytest.mark.parametrize("code", ["event.invalid_transition", "common.not_found", "a_b.c_d"])
def test_valid_codes(code: str) -> None:
    assert e.Conflict(code=code).code == code


@pytest.mark.parametrize("code", ["Event.x", "event", "event.x.y", "event.x-y", "event.", ""])
def test_invalid_code_rejected(code: str) -> None:
    with pytest.raises(ValueError, match="invalid error code"):
        e.Conflict(code=code)


def test_conflict_base_requires_code() -> None:
    with pytest.raises(ValueError, match="invalid error code"):
        e.Conflict()


def test_module_error_subclass() -> None:
    class InvalidTransition(e.Conflict):
        code = "event.invalid_transition"

    err = InvalidTransition("REJECTED -> READY")
    assert (err.code, err.http_status, err.message) == (
        "event.invalid_transition",
        409,
        "REJECTED -> READY",
    )


@pytest.mark.parametrize("cls", [e.RateLimited, e.BudgetExhausted])
def test_retry_after_at_least_one(cls: type[e.RateLimited]) -> None:
    with pytest.raises(ValueError, match="retry_after_s"):
        cls(retry_after_s=0)
    assert cls(retry_after_s=1).retry_after_s == 1


def test_message_defaults_to_title() -> None:
    assert e.NotFound().message == "Not found"
