"""Cookie сессии (BE-T0.14 §7; CONV §15.7: `__Host-` требует Secure, на localhost — `sid`)."""

from datetime import datetime

from starlette.requests import Request
from starlette.responses import Response

_INSECURE_ENVS = {"local", "e2e"}


def cookie_name(env: str) -> str:
    return "sid" if env in _INSECURE_ENVS else "__Host-sid"


def set_session_cookie(
    response: Response, token: str, absolute_expires_at: datetime, now: datetime, env: str
) -> None:
    response.set_cookie(
        cookie_name(env),
        token,
        max_age=max(0, int((absolute_expires_at - now).total_seconds())),
        path="/",
        secure=env not in _INSECURE_ENVS,
        httponly=True,
        samesite="lax",
    )


def clear_session_cookie(response: Response, env: str) -> None:
    response.delete_cookie(
        cookie_name(env), path="/", secure=env not in _INSECURE_ENVS, httponly=True, samesite="lax"
    )


def session_token(request: Request, env: str) -> str | None:
    return request.cookies.get(cookie_name(env)) or None
