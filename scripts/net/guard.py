"""Outbound-request guard: refuse any request that would reach a non-public address.

Users can add domains to a watchlist, and the server then fetches them, so every
outbound fetch is a potential SSRF (cloud metadata, Fly's private network,
localhost). The check runs on every request including each redirect hop.

Residual risk: DNS can change between this check and the connection (rebinding).
Closing that fully needs a connect-time address pin; this guard stops the direct
and redirect cases, which is what a user-supplied domain list can reach.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Callable

import httpx


class BlockedAddress(httpx.TransportError):
    """A request would reach a non-public address. Subclasses httpx.TransportError so existing
    `except httpx.HTTPError` handlers record it as a failed fetch instead of crashing."""


_NAT64 = ipaddress.ip_network("64:ff9b::/96")
_SIIT = ipaddress.ip_network("::ffff:0:0:0/96")
_ALWAYS_BLOCKED = tuple(
    ipaddress.ip_network(n) for n in ("::/96", "64:ff9b:1::/48", "fec0::/10")
)


def _embedded_ipv4(address: ipaddress.IPv6Address) -> ipaddress.IPv4Address | None:
    """The IPv4 address an IPv6 address wraps (mapped, 6to4, NAT64, SIIT), if any."""
    if address.ipv4_mapped is not None:
        return address.ipv4_mapped
    if address.sixtofour is not None:
        return address.sixtofour
    if address in _NAT64 or address in _SIIT:
        return ipaddress.IPv4Address(int(address) & 0xFFFFFFFF)
    return None


def _is_public(raw: str) -> bool:
    address = ipaddress.ip_address(raw.split("%")[0])
    if address.version == 6:
        if any(address in net for net in _ALWAYS_BLOCKED):
            return False
        embedded = _embedded_ipv4(address)
        if embedded is not None:
            address = embedded
    return address.is_global and not address.is_multicast


def _resolve_addresses(host: str, resolver: Callable | None) -> list[str]:
    lookup = resolver or socket.getaddrinfo
    try:
        infos = lookup(host, None)
        addresses = sorted({info[4][0] for info in infos})
        if not addresses:
            raise BlockedAddress(f"{host} has no addresses")
        bad = [a for a in addresses if not _is_public(a)]
    except BlockedAddress:
        raise
    except Exception as exc:  # any resolve/parse failure is a failed fetch, never a crash
        raise BlockedAddress(f"{host} could not be checked ({exc.__class__.__name__})") from exc
    if bad:
        raise BlockedAddress(f"{host} resolves to a non-public address ({bad[0]})")
    return addresses


def assert_public_host(host: str, resolver: Callable | None = None) -> None:
    """Raise BlockedAddress unless every address `host` resolves to is globally routable."""
    if not host:
        raise BlockedAddress("empty host")
    _resolve_addresses(host, resolver)


async def _check_request(request: httpx.Request) -> None:
    await asyncio.to_thread(assert_public_host, request.url.host)


def guarded_client(**kwargs) -> httpx.AsyncClient:
    """An AsyncClient that checks every request, redirects included."""
    hooks = dict(kwargs.pop("event_hooks", {}))
    hooks["request"] = [_check_request, *hooks.get("request", [])]
    return httpx.AsyncClient(event_hooks=hooks, **kwargs)
