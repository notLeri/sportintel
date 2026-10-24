import ipaddress
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

from sportintel.modules.sources.domain.values import (
    DEFAULT_PARSER_PROFILES,
    ContentPolicy,
    SourceHealth,
    SourceKind,
    SourceTier,
)
from sportintel.platform.errors import FieldError, ValidationFailed

_DOMAIN_RE = re.compile(r"^[a-z0-9.-]+\.[a-z]{2,}$")
_PUNY_TLD_RE = re.compile(r"^[a-z0-9.-]+\.(?:[a-z]{2,}|xn--[a-z0-9-]+)$")
_OWNER_RE = re.compile(r"^[a-z0-9_]{2,40}$")
MAX_URL = 2048


def normalize_domain(url_or_host: str) -> str:
    """`https://WWW.Lance.com.br:443/x` → `lance.com.br`; IDN → punycode."""
    raw = url_or_host.strip()
    host = urlsplit(raw).hostname if "://" in raw else raw.split("/", 1)[0].rsplit(":", 1)[0]
    host = (host or "").strip(".").lower()
    host = host.removeprefix("www.")
    try:
        return host.encode("idna").decode("ascii")
    except UnicodeError:
        return host


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value.strip("[]"))
    except ValueError:
        return False
    return True


def _is_http_url(value: str) -> bool:
    parts = urlsplit(value)
    return parts.scheme in {"http", "https"} and bool(parts.hostname) and len(value) <= MAX_URL


@dataclass
class Source:
    id: uuid.UUID
    name: str
    domain: str
    base_url: str
    kind: SourceKind
    feed_urls: list[str] = field(default_factory=list)
    parser_profile: str = "default"
    tier: SourceTier | None = None
    owner_group: str | None = None
    language: str = "en"
    region: str = "BR"  # ISO 3166-1 alpha-2: юрисдикция/страна источника
    poll_interval_seconds: int = 300
    min_request_gap_ms: int = 2000
    content_policy: ContentPolicy = ContentPolicy.TRANSIENT_TEXT
    content_ttl_days: int = 7
    url_keep_params: list[str] = field(default_factory=list)
    tos_notes: str = ""
    active: bool = True
    health: SourceHealth = SourceHealth.UNKNOWN
    consecutive_failures: int = 0
    next_poll_at: datetime | None = None
    last_success_at: datetime | None = None
    last_new_article_at: datetime | None = None
    feed_cache: dict[str, Any] = field(default_factory=dict)
    version: int = 1

    normalize_domain = staticmethod(normalize_domain)

    def validate(self, known_profiles: frozenset[str] = DEFAULT_PARSER_PROFILES) -> None:
        """Все нарушения сразу — одним ValidationFailed (BE-T1.1 §11)."""
        errs: list[FieldError] = []

        def bad(name: str, code: str, msg: str) -> None:
            errs.append(FieldError(name, code, msg))

        if not 1 <= len(self.name.strip()) <= 120:
            bad("name", "length", "name must be 1–120 characters")
        self.domain = normalize_domain(self.domain)
        # manual: URL на IP принимается, а worker пометит статью ssrf_blocked (BE-T1.10 §12)
        ip_manual = self.kind == SourceKind.MANUAL and _is_ip(self.domain)
        if not (
            ip_manual or _DOMAIN_RE.fullmatch(self.domain) or _PUNY_TLD_RE.fullmatch(self.domain)
        ):
            bad("domain", "invalid", "domain must look like example.com")
        if not _is_http_url(self.base_url):
            bad("base_url", "invalid", "base_url must be an absolute http(s) URL")
        else:
            host = normalize_domain(self.base_url)
            if host != self.domain and not host.endswith("." + self.domain):
                bad(
                    "base_url", "host_mismatch", "base_url host must be the domain or its subdomain"
                )
        if self.kind != SourceKind.MANUAL and not self.feed_urls:
            bad("feed_urls", "required", f"{self.kind} source needs at least one feed URL")
        # default читает только RSS/Atom/sitemap: страница или JSON дали бы 0 статей без ошибки
        if self.kind in {SourceKind.HTML, SourceKind.CALENDAR} and self.parser_profile == "default":
            bad(
                "parser_profile",
                "kind_mismatch",
                f"{self.kind} source needs its own parser profile",
            )
        if self.kind == SourceKind.MANUAL and self.feed_urls:
            bad("feed_urls", "not_allowed", "manual source has no feeds")
        for i, url in enumerate(self.feed_urls):
            if not _is_http_url(url):
                bad(f"feed_urls.{i}", "invalid", "feed URL must be http(s), ≤ 2048 characters")
        if not 60 <= self.poll_interval_seconds <= 86400:
            bad("poll_interval_seconds", "range", "must be 60–86400")
        if not 500 <= self.min_request_gap_ms <= 60000:
            bad("min_request_gap_ms", "range", "must be 500–60000")
        if not 1 <= self.content_ttl_days <= 30:
            bad("content_ttl_days", "range", "must be 1–30")
        if self.parser_profile not in known_profiles:
            known = ", ".join(sorted(known_profiles))
            bad("parser_profile", "unknown_profile", f"known profiles: {known}")
        if self.owner_group is not None and not _OWNER_RE.fullmatch(self.owner_group):
            bad("owner_group", "invalid", "owner_group must match ^[a-z0-9_]{2,40}$")
        if not re.fullmatch(r"[A-Z]{2}", self.region):
            bad("region", "invalid", "region must be an ISO 3166-1 alpha-2 code, e.g. BR")
        if errs:
            raise ValidationFailed(details=errs)

    @property
    def polls(self) -> bool:
        return self.active and self.kind != SourceKind.MANUAL
