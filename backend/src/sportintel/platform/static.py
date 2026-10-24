"""Раздача собранного SPA из того же процесса web (INFRA-T0.10, ARCHITECTURE §29.1)."""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

_NOT_SPA_PREFIXES = ("/api", "/auth", "/healthz", "/readyz")
_IMMUTABLE = "public, max-age=31536000, immutable"


class _ImmutableStatic(StaticFiles):
    """Файлы в /assets содержат хэш в имени — кэшируются навсегда."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = _IMMUTABLE
        return response


def mount_spa(app: FastAPI, static_dir: str, *, env: str, oidc: bool = True) -> bool:
    """Подключить SPA, если каталог сборки существует (в local его обычно нет)."""
    root = Path(static_dir).resolve()
    index = root / "index.html"
    if not index.is_file():
        return False
    if (root / "assets").is_dir():
        app.mount("/assets", _ImmutableStatic(directory=root / "assets"), name="assets")

    # Образ один на все окружения: ENV и доступность входа через IdP подставляются при отдаче.
    index_html = (
        index.read_text().replace("%APP_ENV%", env).replace("%APP_OIDC%", "on" if oidc else "off")
    )

    @app.get("/{path:path}", include_in_schema=False, openapi_extra={"x-permission": "public"})
    async def spa(path: str, request: Request) -> Response:
        if request.url.path.startswith(_NOT_SPA_PREFIXES):
            raise StarletteHTTPException(status_code=404)
        candidate = (root / path).resolve()
        # Корневые файлы сборки (favicon, robots.txt); выход за пределы каталога запрещён.
        if path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        return HTMLResponse(index_html, headers={"Cache-Control": "no-cache"})

    return True
