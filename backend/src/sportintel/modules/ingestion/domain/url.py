"""Канонический URL статьи — ключ дедупликации (BE-T1.5)."""

import re
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

_UNRESERVED = re.compile(r"[A-Za-z0-9\-._~]")
_PCT = re.compile(r"%([0-9A-Fa-f]{2})")
_SAFE_PATH = "/:@!$&'()*+,;=-._~%"
_DEFAULT_PORTS = {"http": 80, "https": 443}
_TRACKING = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
    "cmpid",
    "__twitter_impression",
    "amp",
    "outputtype",
}


def _normalize_pct(match: re.Match[str]) -> str:
    """Раскодировать только unreserved-символы; остальные — в верхний регистр hex."""
    char = chr(int(match.group(1), 16))
    return char if _UNRESERVED.fullmatch(char) else f"%{match.group(1).upper()}"


def _host(raw: str) -> str:
    host = raw.lower().strip(".")
    try:
        return host.encode("idna").decode("ascii")
    except UnicodeError:
        return host


def _path(raw: str) -> str:
    path = _PCT.sub(_normalize_pct, raw)
    path = quote(path, safe=_SAFE_PATH)  # не-ASCII (ã, ç, кириллица) → %XX
    path = re.sub(r"/{2,}", "/", path) or "/"
    if path.startswith("/amp/"):
        path = path[len("/amp") :]
    for suffix in ("/amp", ".amp"):
        if path.endswith(suffix) and path != suffix:
            path = path[: -len(suffix)]
    if len(path) > 1:
        path = path.rstrip("/") or "/"
    return path


def _is_tracking(name: str) -> bool:
    low = name.lower()
    return low.startswith("utm_") or low in _TRACKING


def canonicalize(url: str, keep_params: frozenset[str] = frozenset()) -> str:
    raw = url.strip()
    parts = urlsplit(raw)
    if not parts.scheme or "://" not in raw:
        raise ValueError("URL without scheme")
    scheme = parts.scheme.lower()
    if scheme not in _DEFAULT_PORTS:
        raise ValueError(f"scheme {scheme!r} is not http(s)")
    if not parts.hostname:
        raise ValueError("URL without host")
    host = _host(parts.hostname)
    if ":" in host:  # IPv6-литерал
        host = f"[{host}]"
    try:
        port = parts.port
    except ValueError:
        raise ValueError("invalid port") from None
    netloc = host if port in (None, _DEFAULT_PORTS[scheme]) else f"{host}:{port}"
    # Новостные сайты почти не идентифицируют статью query: оставляем только keep_params.
    query = sorted(
        (
            (k, v)
            for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if k in keep_params and not _is_tracking(k)
        ),
        key=lambda kv: kv[0],
    )
    return urlunsplit((scheme, netloc, _path(parts.path), urlencode(query, quote_via=quote), ""))
