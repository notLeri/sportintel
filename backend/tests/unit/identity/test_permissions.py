import pytest
from fastapi import APIRouter

from sportintel.modules.identity import public as identity
from sportintel.modules.identity.domain.permissions import ROLE_PERMISSIONS, has_permission
from sportintel.modules.identity.domain.values import Role

# «Вторая подпись»: таблица CONV §8 переписана вручную.
# Расхождение с кодом — ошибка в одном из мест.
R, E, A = "researcher", "editor", "admin"
MATRIX = {
    "self.read": {R, E, A},
    "events.read": {R, E, A},
    "events.edit": {R, E, A},
    "events.transition": {R, E, A},
    "events.merge": {R, E, A},
    "events.override_assessment": {E, A},
    "events.resolve_conflict": {E, A},
    "drafts.write": {R, E, A},
    "articles.read": {R, E, A},
    "articles.create": {R, E, A},
    "sources.read": {R, E, A},
    "taxonomy.read": {R, E, A},
    "audit.read": {E, A},
    "analytics.read": {E, A},
    "sources.manage": {A},
    "taxonomy.manage": {A},
    "settings.manage": {A},
    "users.manage": {A},
    "pipeline.manage": {A},
    "channels.manage": {A},
}


def test_permission_enum_matches_conv() -> None:
    assert {p.value for p in identity.Permission} == set(MATRIX)


@pytest.mark.parametrize("perm", sorted(MATRIX))
def test_matrix_row(perm: str) -> None:
    holders = {role.value for role, perms in ROLE_PERMISSIONS.items() if perm in perms}
    assert holders == MATRIX[perm]


def test_has_permission() -> None:
    assert has_permission(Role.EDITOR, identity.Permission.AUDIT_READ)
    assert not has_permission("researcher", identity.Permission.USERS_MANAGE)


def test_route_without_permission_is_rejected_at_build_time() -> None:
    router = APIRouter(route_class=identity.PermissionedRoute)
    with pytest.raises(ValueError, match="x-permission"):

        @router.get("/x")
        async def x() -> None: ...


def test_unknown_permission_is_rejected() -> None:
    router = APIRouter(route_class=identity.PermissionedRoute)
    with pytest.raises(ValueError, match=r"events\.fly"):

        @router.get("/y", openapi_extra={"x-permission": "events.fly"})
        async def y() -> None: ...
