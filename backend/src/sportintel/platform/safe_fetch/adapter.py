"""SafeHttpFetcher: единственная сетевая поверхность к недоверенным хостам (BE-T1.3)."""

import asyncio
import ipaddress
import time
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
import structlog

from sportintel.platform.safe_fetch.errors import FetchError
from sportintel.platform.safe_fetch.ip_policy import resolve_and_check
from sportintel.platform.safe_fetch.port import FetchRequest, FetchResponse

MAX_URL = 2048
MAX_REDIRECTS = 5
ALLOWED_PORTS = {80, 443, 8080, 8443}
_REDIRECTS = {301, 302, 303, 307, 308}
_ACCEPT_HEADER = {
    "feed": (
        "application/rss+xml, application/atom+xml, application/xml;q=0.9, "
        "text/xml;q=0.9, */*;q=0.5"
    ),
    "html": "text/html, application/xhtml+xml;q=0.9, */*;q=0.5",
    "any": "*/*",
}
_ALLOWED_TYPES = {
    "feed": {
        "application/rss+xml",
        "application/atom+xml",
        "application/xml",
        "text/xml",
        "text/html",
    },
    "html": {"text/html", "application/xhtml+xml"},
}
_log = structlog.get_logger("sportintel.safe_fetch")


def _check_url(url: str, allow_hosts: frozenset[str]) -> tuple[str, str, int]:
    """→ (scheme, host, port). Схема http(s), без userinfo, разрешённый порт, ≤ 2048."""
    if len(url) > MAX_URL:
        raise FetchError("ssrf_blocked", "URL longer than 2048", permanent=True)
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"}:
        raise FetchError("ssrf_blocked", f"scheme {parts.scheme!r} not allowed", permanent=True)
    if parts.username is not None or parts.password is not None:
        raise FetchError("ssrf_blocked", "userinfo in URL", permanent=True)
    host = parts.hostname
    if not host:
        raise FetchError("ssrf_blocked", "URL without host", permanent=True)
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError:
        raise FetchError("ssrf_blocked", "invalid port", permanent=True) from None
    # ponytail: e2e/тестовые хосты из allowlist ходят и на нестандартные порты.
    if port not in ALLOWED_PORTS and host not in allow_hosts:
        raise FetchError("ssrf_blocked", f"port {port} not allowed", permanent=True)
    return parts.scheme, host, port


def _pinned_url(url: str, ip: str) -> str:
    parts = urlsplit(url)
    host = f"[{ip}]" if ":" in ip else ip
    netloc = f"{host}:{parts.port}" if parts.port else host
    return urlunsplit((parts.scheme, netloc, parts.path or "/", parts.query, ""))


def _host_header(url: str) -> str:
    parts = urlsplit(url)
    host = parts.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    return f"{host}:{parts.port}" if parts.port else host


def _media_type(headers: httpx.Headers) -> str:
    return headers.get("content-type", "").split(";", 1)[0].strip().lower()


class SafeHttpFetcher:
    def __init__(
        self,
        user_agent: str,
        allow_hosts: frozenset[str] = frozenset(),
        allow_fake_ip: bool = False,
    ) -> None:
        self.user_agent = user_agent
        self.allow_hosts = allow_hosts
        self.allow_fake_ip = allow_fake_ip

    async def fetch(self, req: FetchRequest) -> FetchResponse:
        started = time.perf_counter()
        url, redirects = req.url, list[str]()
        try:
            async with asyncio.timeout(req.timeout_s):
                for _ in range(MAX_REDIRECTS + 1):
                    result = await self._hop(url, req)
                    if isinstance(result, FetchResponse):
                        resp = FetchResponse(
                            **{
                                **result.__dict__,
                                "elapsed_ms": int((time.perf_counter() - started) * 1000),
                                "redirects": tuple(redirects),
                            }
                        )
                        _log.info(
                            "platform.fetch_completed",
                            host=urlsplit(resp.final_url).hostname,
                            status=resp.status,
                            elapsed_ms=resp.elapsed_ms,
                            bytes=len(resp.body),
                        )
                        return resp
                    nxt = urljoin(url, result)
                    if urlsplit(url).scheme == "https" and urlsplit(nxt).scheme == "http":
                        raise FetchError("ssrf_blocked", "https → http redirect", permanent=True)
                    redirects.append(nxt)
                    url = nxt
                raise FetchError(
                    "fetch_http_4xx", f"more than {MAX_REDIRECTS} redirects", permanent=True
                )
        except TimeoutError:
            raise FetchError(
                "fetch_timeout", f"no response in {req.timeout_s}s", permanent=False
            ) from None
        except FetchError:
            raise
        except httpx.TimeoutException:
            raise FetchError("fetch_timeout", "timeout", permanent=False) from None
        except httpx.HTTPError as e:
            raise FetchError("fetch_network", type(e).__name__, permanent=False) from None
        except Exception as e:  # неожиданное — не роняем задачу, но видим в логе
            _log.warning("platform.fetch_unexpected_error", error=type(e).__name__)
            raise FetchError("fetch_network", type(e).__name__, permanent=False) from None

    async def _hop(self, url: str, req: FetchRequest) -> FetchResponse | str:
        """Один запрос. → ответ или Location следующего редиректа."""
        _, host, port = _check_url(url, self.allow_hosts)
        ips = await resolve_and_check(host, port, self.allow_hosts, self.allow_fake_ip)
        last_error: httpx.ConnectError | None = None
        for ip in ips:  # все адреса уже проверены; перебор — только при отказе подключения
            try:
                return await self._request(url, host, ip, req)
            except httpx.ConnectError as e:
                last_error = e
        assert last_error is not None  # noqa: S101 — ips непуст (resolve_and_check)
        raise last_error

    async def _request(
        self, url: str, host: str, ip: str, req: FetchRequest
    ) -> FetchResponse | str:
        headers = {
            "Host": _host_header(url),
            "User-Agent": self.user_agent,
            "Accept": _ACCEPT_HEADER[req.accept],
            "Accept-Language": "en,ru;q=0.9,pt-BR;q=0.8",
        }
        if req.etag:
            headers["If-None-Match"] = req.etag
        if req.last_modified:
            headers["If-Modified-Since"] = req.last_modified
        # Подключение к уже проверенному IP (без повторного DNS); SNI и Host — исходный хост,
        # поэтому TLS-сертификат проверяется по имени (BE-T1.3 §22).
        extensions = {} if _is_ip(host) else {"sni_hostname": host}
        async with (
            httpx.AsyncClient(follow_redirects=False, trust_env=False) as client,
            client.stream(
                "GET", _pinned_url(url, ip), headers=headers, extensions=extensions
            ) as response,
        ):
            status = response.status_code
            if status in _REDIRECTS and "location" in response.headers:
                return response.headers["location"]
            if status == 304:
                return self._response(url, response, b"", not_modified=True)
            if status == 408 or status == 429:
                raise FetchError("fetch_http_4xx", f"HTTP {status}", permanent=False)
            if status >= 500:
                raise FetchError("fetch_http_5xx", f"HTTP {status}", permanent=False)
            if status >= 400:
                raise FetchError("fetch_http_4xx", f"HTTP {status}", permanent=True)
            media = _media_type(response.headers)
            allowed = _ALLOWED_TYPES.get(req.accept)
            if allowed is not None and media not in allowed:
                raise FetchError("fetch_bad_content_type", media or "missing", permanent=True)
            body = bytearray()
            # aiter_bytes отдаёт декодированные (gzip/br) байты: лимит защищает от zip-бомб.
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > req.max_bytes:
                    raise FetchError("fetch_too_large", f"> {req.max_bytes} bytes", permanent=True)
            return self._response(url, response, bytes(body), not_modified=False)

    @staticmethod
    def _response(url: str, r: httpx.Response, body: bytes, *, not_modified: bool) -> FetchResponse:
        return FetchResponse(
            final_url=url,
            status=r.status_code,
            headers=dict(r.headers),
            content_type=_media_type(r.headers),
            body=body,
            etag=r.headers.get("etag"),
            last_modified=r.headers.get("last-modified"),
            not_modified=not_modified,
            elapsed_ms=0,
        )


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True
