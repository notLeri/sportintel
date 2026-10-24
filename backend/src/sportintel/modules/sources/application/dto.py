import uuid
from dataclasses import dataclass

from sportintel.modules.sources.domain.source import Source


@dataclass(frozen=True)
class SourceMeta:
    """То, что другим модулям нужно знать об источнике (фасад sources.public)."""

    id: uuid.UUID
    name: str
    domain: str
    kind: str
    tier: str | None
    owner_group: str | None
    language: str
    region: str
    parser_profile: str
    content_policy: str
    content_ttl_days: int
    min_request_gap_ms: int
    url_keep_params: tuple[str, ...]
    feed_urls: tuple[str, ...]
    active: bool
    health: str = "unknown"

    @staticmethod
    def of(s: Source) -> "SourceMeta":
        return SourceMeta(
            id=s.id,
            name=s.name,
            domain=s.domain,
            kind=s.kind.value,
            tier=s.tier.value if s.tier else None,
            owner_group=s.owner_group,
            language=s.language,
            region=s.region,
            parser_profile=s.parser_profile,
            content_policy=s.content_policy.value,
            content_ttl_days=s.content_ttl_days,
            min_request_gap_ms=s.min_request_gap_ms,
            url_keep_params=tuple(s.url_keep_params),
            feed_urls=tuple(s.feed_urls),
            active=s.active,
            health=s.health.value,
        )
