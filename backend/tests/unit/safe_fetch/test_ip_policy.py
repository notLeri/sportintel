import ipaddress

import pytest

from sportintel.platform.safe_fetch import FetchError
from sportintel.platform.safe_fetch.adapter import _check_url
from sportintel.platform.safe_fetch.ip_policy import is_forbidden_ip, resolve_and_check


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "10.1.2.3",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.169.254",
        "100.64.1.1",
        "::1",
        "fe80::1",
        "fd12::1",
        "::ffff:127.0.0.1",
        "0.0.0.0",  # noqa: S104 — адрес из списка запрещённых, не bind
        "224.0.0.1",
        "64:ff9b::a00:1",
    ],
)
def test_forbidden(ip: str) -> None:
    assert is_forbidden_ip(ipaddress.ip_address(ip))


@pytest.mark.parametrize("ip", ["8.8.8.8", "2001:4860:4860::8888", "200.147.67.142"])
def test_allowed(ip: str) -> None:
    assert not is_forbidden_ip(ipaddress.ip_address(ip))


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "gopher://example.com/",
        "ftp://example.com/",
        "http://user:pass@example.com/",
        "http://example.com:22/",
        "http://example.com:99999/",
        "https:///nohost",
        "https://example.com/" + "a" * 2050,
    ],
)
def test_url_rules_block(url: str) -> None:
    with pytest.raises(FetchError) as e:
        _check_url(url, frozenset())
    assert e.value.code == "ssrf_blocked"
    assert e.value.permanent


@pytest.mark.parametrize(
    ("url", "port"),
    [
        ("http://example.com/", 80),
        ("https://example.com/x", 443),
        ("https://example.com:8443/", 8443),
    ],
)
def test_url_rules_pass(url: str, port: int) -> None:
    assert _check_url(url, frozenset())[2] == port


def test_allowlisted_host_may_use_any_port() -> None:
    assert _check_url("http://fake-source:9000/feed", frozenset({"fake-source"}))[2] == 9000


async def test_fake_ip_allowed_only_with_flag() -> None:
    # 198.18.0.1 — литерал, getaddrinfo не ходит в DNS
    with pytest.raises(FetchError, match="forbidden"):
        await resolve_and_check("198.18.0.1", 443, frozenset())
    assert await resolve_and_check("198.18.0.1", 443, frozenset(), allow_fake_ip=True) == [
        "198.18.0.1"
    ]
    with pytest.raises(FetchError, match="forbidden"):  # остальные приватные — по-прежнему нет
        await resolve_and_check("10.0.0.1", 443, frozenset(), allow_fake_ip=True)
