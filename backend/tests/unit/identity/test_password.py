from sportintel.modules.identity.domain.password import (
    MAX_LENGTH,
    hash_password,
    password_problem,
    verify_password,
)


def test_hash_roundtrip_and_salt() -> None:
    h = hash_password("correct horse battery")
    assert h.startswith("scrypt$")
    assert verify_password("correct horse battery", h)
    assert not verify_password("correct horse batterY", h)
    assert hash_password("correct horse battery") != h  # соль своя у каждого хэша


def test_broken_or_missing_hash_is_just_false() -> None:
    for stored in (None, "", "plain", "bcrypt$1$2$3$aa$bb", "scrypt$x$8$1$zz$00"):
        assert not verify_password("whatever-long", stored)


def test_too_long_password_not_hashed() -> None:
    h = hash_password("a" * 12)
    assert not verify_password("a" * (MAX_LENGTH + 1), h)


def test_password_problem() -> None:
    assert password_problem("short") == "too_short"
    assert password_problem("x" * (MAX_LENGTH + 1)) == "too_long"
    assert password_problem("long enough pw") is None
