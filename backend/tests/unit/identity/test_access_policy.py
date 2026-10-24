from dataclasses import replace

import pytest

from sportintel.modules.identity.domain.access_policy import (
    Allow,
    Deny,
    OidcIdentity,
    decide_access,
    sanitize_next,
)
from sportintel.modules.identity.domain.user import User
from sportintel.modules.identity.domain.values import Locale, Role
from sportintel.platform.ids import new_id

IDENT = OidcIdentity("sub-1", "ana@corp.com", True, "Ana", "corp.com")
USER = User(
    id=new_id(),
    email="ana@corp.com",
    display_name="Ana",
    role=Role.EDITOR,
    locale=Locale.PT_BR,
    timezone="America/Sao_Paulo",
    hotkeys_enabled=True,
    active=True,
    invited=False,
    oidc_subject="sub-1",
    last_login_at=None,
    version=1,
)


def decide(identity=IDENT, user=None, domains=frozenset(), boot=None, admin_exists=False):  # type: ignore[no-untyped-def]
    return decide_access(identity, user, set(domains), boot, admin_exists)


def test_rule1_unverified_email_denied_even_for_existing_admin() -> None:
    assert decide(replace(IDENT, email_verified=False), replace(USER, role=Role.ADMIN)) == Deny(
        "auth.email_not_verified"
    )


def test_rule2_inactive_user_denied() -> None:
    assert decide(user=replace(USER, active=False), domains={"corp.com"}) == Deny(
        "auth.user_inactive"
    )


def test_rule3_existing_user_allowed_without_domain() -> None:
    assert decide(user=USER) == Allow(None)
    invited = replace(USER, invited=True, oidc_subject=None, email="guest@gmail.com")
    assert decide(replace(IDENT, email="guest@gmail.com"), invited) == Allow(None)


def test_rule3_subject_mismatch_denied() -> None:
    d = decide(user=replace(USER, oidc_subject="someone-else"))
    assert d == Deny("auth.not_allowed", subject_mismatch=True)


def test_rule4_bootstrap_admin_only_while_no_admin() -> None:
    assert decide(boot="ANA@corp.com") == Allow(Role.ADMIN)
    assert decide(boot="ana@corp.com", admin_exists=True) == Deny("auth.not_allowed")
    assert decide(boot="ana@corp.com", admin_exists=True, domains={"corp.com"}) == Allow(
        Role.RESEARCHER
    )


def test_rule5_allowed_domain_from_email_not_hd() -> None:
    assert decide(domains={"Corp.com"}) == Allow(Role.RESEARCHER)
    spoof = replace(IDENT, email="x@evil.com", hosted_domain="corp.com")
    assert decide(spoof, domains={"corp.com"}) == Deny("auth.not_allowed")


def test_rule6_default_deny() -> None:
    assert decide() == Deny("auth.not_allowed")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, "/"),
        ("", "/"),
        ("/ok?x=1", "/ok?x=1"),
        ("/events/1#t", "/events/1#t"),
        ("//evil.com", "/"),
        ("https://evil.com", "/"),
        ("/\\evil.com", "/"),
        ("evil", "/"),
    ],
)
def test_sanitize_next(raw: str | None, expected: str) -> None:
    assert sanitize_next(raw) == expected
