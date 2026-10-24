import gzip
import time

import pytest
from pytest_httpserver import HTTPServer
from werkzeug import Request, Response

from sportintel.platform.safe_fetch import FetchError, FetchRequest, SafeHttpFetcher

LOCAL = frozenset({"127.0.0.1", "localhost"})
RSS = b"<?xml version='1.0'?><rss><channel><item><title>x</title></item></channel></rss>"


def fetcher(allow: frozenset[str] = LOCAL) -> SafeHttpFetcher:
    return SafeHttpFetcher("SportIntelBot/1.0 (+test)", allow)


async def code_of(f: SafeHttpFetcher, req: FetchRequest) -> str:
    with pytest.raises(FetchError) as e:
        await f.fetch(req)
    return e.value.code


async def test_loopback_without_allowlist_blocked(httpserver: HTTPServer) -> None:
    httpserver.expect_request("/feed").respond_with_data(RSS, content_type="application/rss+xml")
    url = f"http://localhost:{httpserver.port}/feed".replace(f":{httpserver.port}", ":8080")
    assert await code_of(fetcher(frozenset()), FetchRequest(url, "feed")) == "ssrf_blocked"
    assert (
        await code_of(fetcher(frozenset()), FetchRequest("http://[::1]/", "any")) == "ssrf_blocked"
    )
    assert (
        await code_of(fetcher(frozenset()), FetchRequest("http://2130706433/", "any"))
        == "ssrf_blocked"
    )


async def test_ok_with_headers(httpserver: HTTPServer) -> None:
    seen: dict[str, str] = {}

    def handler(request: Request) -> Response:
        seen.update({k.lower(): v for k, v in request.headers.items()})
        return Response(
            RSS, content_type="application/rss+xml; charset=utf-8", headers={"ETag": '"v1"'}
        )

    httpserver.expect_request("/feed").respond_with_handler(handler)
    r = await fetcher().fetch(FetchRequest(httpserver.url_for("/feed"), "feed"))
    assert (r.status, r.content_type, r.body, r.etag, r.not_modified) == (
        200,
        "application/rss+xml",
        RSS,
        '"v1"',
        False,
    )
    assert seen["user-agent"] == "SportIntelBot/1.0 (+test)"
    assert seen["accept-language"].startswith("en")
    assert "cookie" not in seen


async def test_redirect_to_metadata_blocked(httpserver: HTTPServer) -> None:
    httpserver.expect_request("/r").respond_with_data(
        "", status=302, headers={"Location": "http://169.254.169.254/latest/meta-data/"}
    )
    assert await code_of(fetcher(), FetchRequest(httpserver.url_for("/r"), "any")) == "ssrf_blocked"


async def test_redirect_chain_followed_and_limited(httpserver: HTTPServer) -> None:
    for i in range(7):
        httpserver.expect_request(f"/r{i}").respond_with_data(
            "", status=301, headers={"Location": f"/r{i + 1}"}
        )
    httpserver.expect_request("/r3_ok").respond_with_data(RSS, content_type="text/xml")
    httpserver.expect_request("/a").respond_with_data(
        "", status=302, headers={"Location": "/r3_ok"}
    )
    ok = await fetcher().fetch(FetchRequest(httpserver.url_for("/a"), "feed"))
    assert ok.final_url.endswith("/r3_ok")
    assert len(ok.redirects) == 1
    with pytest.raises(FetchError, match="redirects"):
        await fetcher().fetch(FetchRequest(httpserver.url_for("/r0"), "any"))


async def test_too_large_counts_decoded_bytes(httpserver: HTTPServer) -> None:
    bomb = gzip.compress(b"a" * 6_000_000)  # ~6 КБ сжато, 6 МБ после распаковки
    httpserver.expect_request("/big").respond_with_data(
        bomb, content_type="text/html", headers={"Content-Encoding": "gzip"}
    )
    assert (
        await code_of(fetcher(), FetchRequest(httpserver.url_for("/big"), "html"))
        == "fetch_too_large"
    )


async def test_bad_content_type(httpserver: HTTPServer) -> None:
    httpserver.expect_request("/img").respond_with_data(b"\x89PNG", content_type="image/png")
    assert (
        await code_of(fetcher(), FetchRequest(httpserver.url_for("/img"), "html"))
        == "fetch_bad_content_type"
    )


async def test_conditional_get_304(httpserver: HTTPServer) -> None:
    httpserver.expect_request("/feed", headers={"If-None-Match": '"v1"'}).respond_with_data(
        "", status=304
    )
    r = await fetcher().fetch(FetchRequest(httpserver.url_for("/feed"), "feed", etag='"v1"'))
    assert (r.not_modified, r.status, r.body) == (True, 304, b"")


@pytest.mark.parametrize(
    ("status", "code", "permanent"),
    [(404, "fetch_http_4xx", True), (429, "fetch_http_4xx", False), (503, "fetch_http_5xx", False)],
)
async def test_status_mapping(
    httpserver: HTTPServer, status: int, code: str, permanent: bool
) -> None:
    httpserver.expect_request("/s").respond_with_data("x", status=status)
    with pytest.raises(FetchError) as e:
        await fetcher().fetch(FetchRequest(httpserver.url_for("/s"), "any"))
    assert (e.value.code, e.value.permanent) == (code, permanent)


async def test_timeout(httpserver: HTTPServer) -> None:
    def slow(_: Request) -> Response:
        time.sleep(1.5)
        return Response(RSS, content_type="text/xml")

    httpserver.expect_request("/slow").respond_with_handler(slow)
    assert (
        await code_of(fetcher(), FetchRequest(httpserver.url_for("/slow"), "feed", timeout_s=0.3))
        == "fetch_timeout"
    )


async def test_unresolvable_host_is_network_error() -> None:
    assert (
        await code_of(fetcher(frozenset()), FetchRequest("http://does-not-exist.invalid/", "any"))
        == "fetch_network"
    )
