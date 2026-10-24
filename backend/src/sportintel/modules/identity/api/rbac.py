"""RBAC на маршрутах (BE-T0.17): право объявляется в x-permission и проверяется до тела."""

from collections.abc import Callable, Coroutine
from typing import Any, Literal

from fastapi import Depends, Request, Response
from fastapi.routing import APIRoute

from sportintel.modules.identity.api.deps import current_user, optional_user
from sportintel.modules.identity.application.sessions import CurrentUser
from sportintel.modules.identity.domain.permissions import Permission, has_permission
from sportintel.platform.errors import Forbidden, Unauthenticated

PUBLIC = "public"


def route_permission(perm: Permission | Literal["public"]) -> dict[str, Any]:
    return {"x-permission": str(perm)}


def declared_permission(route: APIRoute) -> str | None:
    extra = route.openapi_extra or {}
    value = extra.get("x-permission")
    return str(value) if value is not None else None


async def _check(request: Request, perm: str) -> None:
    if perm == PUBLIC:
        return
    user = await optional_user(request)
    if user is None:
        raise Unauthenticated()
    if not has_permission(user.role, Permission(perm)):
        raise Forbidden()


class PermissionedRoute(APIRoute):
    """Проверяет сессию и право ДО валидации тела: запрещённая роль получает 403, а не 422.

    Маршрут без x-permission отклоняется при сборке (отказ по умолчанию).
    """

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        # Вызывается из APIRoute.__init__, когда openapi_extra уже присвоен.
        perm = declared_permission(self)
        if perm is None:
            raise ValueError(f"route {self.path} has no x-permission (use route_permission())")
        if perm != PUBLIC:
            Permission(perm)  # неизвестное право — ошибка сборки, а не молчаливый отказ
        handler = super().get_route_handler()

        async def guarded(request: Request) -> Response:
            await _check(request, perm)
            return await handler(request)

        return guarded


def require(perm: Permission) -> Any:
    """Depends: текущий пользователь с правом `perm` (повторная проверка — защита в глубину)."""

    async def dependency(user: CurrentUser = Depends(current_user)) -> CurrentUser:  # noqa: B008
        if not has_permission(user.role, perm):
            raise Forbidden()
        return user

    return Depends(dependency)
