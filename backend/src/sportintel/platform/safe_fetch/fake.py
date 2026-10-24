"""FakeHttpFetcher для unit/integration тестов (CONV §13): без сети."""

from sportintel.platform.safe_fetch.errors import FetchError
from sportintel.platform.safe_fetch.port import FetchRequest, FetchResponse


def ok(
    url: str, body: bytes | str, content_type: str = "application/rss+xml", **kw: object
) -> FetchResponse:
    data = body.encode() if isinstance(body, str) else body
    return FetchResponse(
        final_url=str(kw.pop("final_url", url)),
        status=int(kw.pop("status", 200)),  # type: ignore[call-overload]
        headers={"content-type": content_type},
        content_type=content_type,
        body=data,
        etag=kw.pop("etag", None),  # type: ignore[arg-type]
        last_modified=kw.pop("last_modified", None),  # type: ignore[arg-type]
        not_modified=bool(kw.pop("not_modified", False)),
        elapsed_ms=1,
    )


class FakeHttpFetcher:
    """Маршруты по точному URL; неизвестный URL — fetch_http_4xx (404)."""

    def __init__(self, routes: dict[str, FetchResponse | FetchError] | None = None) -> None:
        self.routes = routes or {}
        self.requests: list[FetchRequest] = []

    async def fetch(self, req: FetchRequest) -> FetchResponse:
        self.requests.append(req)
        result = self.routes.get(req.url)
        if result is None:
            raise FetchError("fetch_http_4xx", "HTTP 404 (fake)", permanent=True)
        if isinstance(result, FetchError):
            raise result
        return result
