from enum import StrEnum


class SourceKind(StrEnum):
    RSS = "rss"
    SITEMAP = "sitemap"
    HTML = "html"
    MANUAL = "manual"
    CALENDAR = "calendar"  # официальный календарь праздников страны (без сети)


class SourceTier(StrEnum):
    OFFICIAL = "OFFICIAL"
    A = "A"
    B = "B"
    C = "C"
    UNTRUSTED = "UNTRUSTED"  # собираем, но не считаем подтверждением (решение редакции)


class ContentPolicy(StrEnum):
    SNIPPET_ONLY = "snippet_only"
    TRANSIENT_TEXT = "transient_text"


class SourceHealth(StrEnum):
    UNKNOWN = "unknown"
    OK = "ok"
    DEGRADED = "degraded"
    DOWN = "down"


# Профили парсинга реализует ingestion (BE-T1.8); sources его не импортирует (CONV §7.2):
# список приходит в validate() из main.py (app.state.known_parser_profiles).
DEFAULT_PARSER_PROFILES = frozenset({"default"})
