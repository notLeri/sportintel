from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal, Protocol

Accept = Literal["feed", "html", "any"]


@dataclass(frozen=True)
class FetchRequest:
    url: str
    accept: Accept
    etag: str | None = None
    last_modified: str | None = None
    max_bytes: int = 5_000_000
    timeout_s: float = 10.0


@dataclass(frozen=True)
class FetchResponse:
    final_url: str
    status: int
    headers: Mapping[str, str]
    content_type: str
    body: bytes
    etag: str | None
    last_modified: str | None
    not_modified: bool
    elapsed_ms: int
    redirects: tuple[str, ...] = field(default_factory=tuple)


class HttpFetcher(Protocol):
    async def fetch(self, req: FetchRequest) -> FetchResponse: ...
