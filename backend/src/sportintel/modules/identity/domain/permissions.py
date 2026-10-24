"""Права и роли — каноническая матрица CONV §8."""

from enum import StrEnum

from sportintel.modules.identity.domain.values import Role


class Permission(StrEnum):
    SELF_READ = "self.read"
    EVENTS_READ = "events.read"
    EVENTS_EDIT = "events.edit"
    EVENTS_TRANSITION = "events.transition"
    EVENTS_MERGE = "events.merge"
    EVENTS_OVERRIDE_ASSESSMENT = "events.override_assessment"
    EVENTS_RESOLVE_CONFLICT = "events.resolve_conflict"
    DRAFTS_WRITE = "drafts.write"
    ARTICLES_READ = "articles.read"
    ARTICLES_CREATE = "articles.create"
    SOURCES_READ = "sources.read"
    TAXONOMY_READ = "taxonomy.read"
    AUDIT_READ = "audit.read"
    ANALYTICS_READ = "analytics.read"
    SOURCES_MANAGE = "sources.manage"
    TAXONOMY_MANAGE = "taxonomy.manage"
    SETTINGS_MANAGE = "settings.manage"
    USERS_MANAGE = "users.manage"
    PIPELINE_MANAGE = "pipeline.manage"
    CHANNELS_MANAGE = "channels.manage"


P = Permission
_RESEARCHER = frozenset(
    {
        P.SELF_READ,
        P.EVENTS_READ,
        P.EVENTS_EDIT,
        P.EVENTS_TRANSITION,
        P.EVENTS_MERGE,
        P.DRAFTS_WRITE,
        P.ARTICLES_READ,
        P.ARTICLES_CREATE,
        P.SOURCES_READ,
        P.TAXONOMY_READ,
    }
)
_EDITOR = _RESEARCHER | {
    P.EVENTS_OVERRIDE_ASSESSMENT,
    P.EVENTS_RESOLVE_CONFLICT,
    P.AUDIT_READ,
    P.ANALYTICS_READ,
}
_ADMIN = frozenset(Permission)

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.RESEARCHER: _RESEARCHER,
    Role.EDITOR: frozenset(_EDITOR),
    Role.ADMIN: _ADMIN,
}


def permissions_for(role: Role | str) -> frozenset[Permission]:
    return ROLE_PERMISSIONS[Role(role)]


def has_permission(role: Role | str, perm: Permission) -> bool:
    return perm in permissions_for(role)
