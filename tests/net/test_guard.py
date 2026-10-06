import socket
from pathlib import Path

import httpx
import pytest

from scripts.net import guard
from scripts.net.guard import BlockedAddress, assert_public_host, guarded_client


def _resolver(*addresses: str):
    def resolve(host, port):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (a, 0)) for a in addresses]

    return resolve


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1", "10.0.0.5", "172.16.3.4", "192.168.1.1",
        "169.254.169.254",          # cloud metadata
        "100.64.0.1",               # carrier-grade NAT
        "0.0.0.0", "::1", "fe80::1", "fdaa::1",
        "::ffff:10.0.0.1",          # IPv4-mapped private
        "224.0.0.1",                # multicast
        "64:ff9b::a00:1", "64:ff9b::7f00:1", "64:ff9b::a9fe:a9fe",  # NAT64 embedding private v4
        "64:ff9b:1::1",             # local-use NAT64
        "::10.0.0.1", "::127.0.0.1", "::a9fe:a9fe",  # IPv4-compatible
        "::ffff:0:10.0.0.1",        # SIIT
        "2002:a00:1::", "2002:a9fe:a9fe::",  # 6to4 embedding private v4
        "fec0::1",                  # deprecated site-local
    ],
)
def test_non_public_addresses_are_blocked(address):
    with pytest.raises(BlockedAddress):
        assert_public_host("anything.example", resolver=_resolver(address))


@pytest.mark.parametrize("address", ["64:ff9b::5db8:d822", "2002:5db8:d822::"])
def test_public_ipv4_embedded_in_ipv6_is_allowed(address):
    assert_public_host("good.example", resolver=_resolver(address))


def test_resolver_exceptions_become_blocked_address():
    def boom(host, port):
        raise UnicodeError("bad idna")

    with pytest.raises(BlockedAddress):
        assert_public_host("xn--.example", resolver=boom)


def test_malformed_address_becomes_blocked_address():
    with pytest.raises(BlockedAddress):
        assert_public_host("odd.example", resolver=_resolver("not-an-ip"))


def test_no_raw_async_client_outside_the_guard():
    root = Path(guard.__file__).resolve().parents[1]
    offenders = [
        str(path)
        for path in root.rglob("*.py")
        if path.name != "guard.py" and "httpx.AsyncClient(" in path.read_text()
    ]
    assert offenders == []


def test_public_address_is_allowed():
    assert_public_host("good.example", resolver=_resolver("93.184.216.34"))


def test_a_mix_of_public_and_private_is_blocked():
    with pytest.raises(BlockedAddress):
        assert_public_host("mixed.example", resolver=_resolver("93.184.216.34", "10.0.0.5"))


def test_unresolvable_host_is_blocked():
    def fail(host, port):
        raise socket.gaierror("no such host")

    with pytest.raises(BlockedAddress):
        assert_public_host("nope.invalid", resolver=fail)


def test_empty_host_is_blocked():
    with pytest.raises(BlockedAddress):
        assert_public_host("")


def test_blocked_address_is_an_httpx_error_so_existing_handlers_catch_it():
    assert issubclass(BlockedAddress, httpx.HTTPError)


@pytest.mark.asyncio
async def test_redirect_to_an_internal_address_is_blocked_before_it_is_requested(monkeypatch):
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data"})

    def fake_getaddrinfo(host, port, *args, **kwargs):
        table = {"good.example": "93.184.216.34", "169.254.169.254": "169.254.169.254"}
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (table[host], 0))]

    monkeypatch.setattr(guard.socket, "getaddrinfo", fake_getaddrinfo)
    async with guarded_client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(BlockedAddress):
            await client.get("http://good.example/", follow_redirects=True)
    assert requested == ["http://good.example/"]


@pytest.mark.asyncio
async def test_a_public_request_goes_through(monkeypatch):
    monkeypatch.setattr(
        guard.socket, "getaddrinfo", lambda host, port, *a, **k: _resolver("93.184.216.34")(host, port)
    )
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text="ok"))
    async with guarded_client(transport=transport) as client:
        assert (await client.get("http://good.example/")).text == "ok"
