"""Реестр профилей парсинга (BE-T1.8)."""

import structlog

from sportintel.modules.ingestion.infrastructure.parsers.base import ParserProfile
from sportintel.modules.ingestion.infrastructure.parsers.cbf import CBF
from sportintel.modules.ingestion.infrastructure.parsers.default import DefaultProfile
from sportintel.modules.ingestion.infrastructure.parsers.holidays import HOLIDAY_PROFILES
from sportintel.modules.ingestion.infrastructure.parsers.telegram import TELEGRAM

DEFAULT = DefaultProfile()
REGISTRY: dict[str, ParserProfile] = {
    p.name: p for p in (DEFAULT, CBF, TELEGRAM, *HOLIDAY_PROFILES)
}
_log = structlog.get_logger("sportintel.ingestion")


def get_profile(name: str) -> ParserProfile:
    profile = REGISTRY.get(name)
    if profile is None:
        _log.error("ingestion.unknown_parser_profile", profile=name)
        return DEFAULT
    return profile


__all__ = ["DEFAULT", "REGISTRY", "ParserProfile", "get_profile"]
