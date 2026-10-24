from datetime import UTC, datetime, timedelta

import pytest
from starlette.responses import Response

from sportintel.modules.identity.api.cookies import clear_session_cookie, set_session_cookie

NOW = datetime(2026, 10, 7, 12, tzinfo=UTC)


@pytest.mark.parametrize(
    ("env", "name", "secure"),
    [("local", "sid", False), ("e2e", "sid", False), ("staging", "__Host-sid", True)],
)
def test_cookie_attributes(env: str, name: str, secure: bool) -> None:
    r = Response()
    set_session_cookie(r, "tok", NOW + timedelta(days=7), NOW, env)
    header = r.headers["set-cookie"]
    assert header.startswith(f"{name}=tok;")
    assert "HttpOnly" in header
    assert "SameSite=lax" in header
    assert "Path=/" in header
    assert "Domain" not in header
    assert "Max-Age=604800" in header
    assert ("Secure" in header) is secure


def test_clear_cookie() -> None:
    r = Response()
    clear_session_cookie(r, "production")
    assert r.headers["set-cookie"].startswith('__Host-sid="";')
