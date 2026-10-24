"""Feature flags из env FLAG_<NAME> (CONV §9). Значения читает config.py."""

import structlog

from sportintel.platform.config import enabled_flags

KNOWN_FLAGS = frozenset({"REQUIRE_SECOND_REVIEWER", "BROWSER_NOTIFICATIONS", "TELEGRAM_PUBLISH"})
_log = structlog.get_logger("sportintel.flags")


def _enabled() -> set[str]:
    return {name.removeprefix("FLAG_") for name in enabled_flags()}


def all_flags() -> dict[str, bool]:
    on = _enabled()
    return {name: name in on for name in sorted(KNOWN_FLAGS)}


def is_enabled(name: str, user: object | None = None) -> bool:
    # ponytail: флаг глобальный; user — задел под таргетинг (D3).
    return name in _enabled()


def warn_unknown_flags() -> None:
    unknown = sorted(_enabled() - KNOWN_FLAGS)
    if unknown:
        _log.warning("platform.unknown_flags", flags=unknown)
