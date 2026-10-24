"""Запрещённые адреса назначения (SSRF, BE-T1.3 §7)."""

import asyncio
import ipaddress
import socket

from sportintel.platform.safe_fetch.errors import FetchError

IP = ipaddress.IPv4Address | ipaddress.IPv6Address

_EXTRA_V4 = (ipaddress.ip_network("100.64.0.0/10"), ipaddress.ip_network("169.254.169.254/32"))
_EXTRA_V6 = (
    ipaddress.ip_network("fd00::/8"),
    ipaddress.ip_network("64:ff9b::/96"),  # NAT64 → может вести во внутреннюю сеть
)
# fake-ip DNS VPN-клиентов (Clash/sing-box/Surge): настоящий адрес резолвит сам VPN.
# ponytail: только IPv4-диапазоны по умолчанию; IPv6 fake-ip добавить, если встретится.
FAKE_IP_NETS = (ipaddress.ip_network("198.18.0.0/15"), ipaddress.ip_network("240.0.0.0/4"))


def is_forbidden_ip(ip: IP) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return is_forbidden_ip(ip.ipv4_mapped)  # ::ffff:127.0.0.1 → проверяем вложенный IPv4
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return True
    extra = _EXTRA_V4 if isinstance(ip, ipaddress.IPv4Address) else _EXTRA_V6
    return any(ip in net for net in extra)


async def resolve_and_check(
    host: str, port: int, allow_hosts: frozenset[str], allow_fake_ip: bool = False
) -> list[str]:
    """Все адреса хоста; если хоть один запрещён — блок (смешанные DNS-ответы, rebinding)."""
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise FetchError("fetch_network", f"DNS: {e}", permanent=False) from None
    ips = list(dict.fromkeys(str(info[4][0]) for info in infos))
    if not ips:
        raise FetchError("fetch_network", "DNS returned no addresses", permanent=False)
    if host not in allow_hosts:
        for raw in ips:
            ip = ipaddress.ip_address(raw.split("%", 1)[0])
            if allow_fake_ip and any(ip in net for net in FAKE_IP_NETS):
                continue
            if is_forbidden_ip(ip):
                raise FetchError(
                    "ssrf_blocked", f"{host} resolves to a forbidden address", permanent=True
                )
    return ips
