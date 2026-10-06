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


def _is_public(raw: str) -> bool:
    address = ipaddress.ip_address(raw.split("%")[0])
    if address.version == 6 and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return address.is_global and not address.is_multicast


def assert_public_host(host: str, resolver: Callable | None = None) -> None:
    """Raise BlockedAddress unless every address `host` resolves to is globally routable."""
    if not host:
        raise BlockedAddress("empty host")
    lookup = resolver or socket.getaddrinfo
    try:
        infos = lookup(host, None)
    except socket.gaierror as exc:
        raise BlockedAddress(f"{host} does not resolve") from exc
    addresses = sorted({info[4][0] for info in infos})
    if not addresses:
        raise BlockedAddress(f"{host} has no addresses")
    bad = [a for a in addresses if not _is_public(a)]
    if bad:
        raise BlockedAddress(f"{host} resolves to a non-public address ({bad[0]})")


async def _check_request(request: httpx.Request) -> None:
    await asyncio.to_thread(assert_public_host, request.url.host)


def guarded_client(**kwargs) -> httpx.AsyncClient:
    """An AsyncClient that checks every request, redirects included."""
    hooks = dict(kwargs.pop("event_hooks", {}))
    hooks["request"] = [_check_request, *hooks.get("request", [])]
    return httpx.AsyncClient(event_hooks=hooks, **kwargs)
