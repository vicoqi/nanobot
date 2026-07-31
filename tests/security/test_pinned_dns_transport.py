"""Tests for the ported ``PinnedDNSAsyncTransport``.

These tests verify the behaviour ported from upstream HKUDS/nanobot: the
transport validates every outgoing request via ``resolve_url_target`` and
rejects unsafe targets (private / loopback / metadata IPs) by raising
``UnsafeHTTPRequestError`` before any network call reaches the inner
transport.  Safe requests are forwarded to the inner transport unchanged.
"""

from __future__ import annotations

import socket
from unittest.mock import patch

import httpx
import pytest

from nanobot.security.network import (
    PinnedDNSAsyncTransport,
    UnsafeHTTPRequestError,
    pin_resolved_url_dns,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

class _RecordingTransport(httpx.AsyncBaseTransport):
    """A fake inner transport that records the requests it receives."""

    def __init__(self) -> None:
        self.calls: list[httpx.Request] = []
        self.closed = False

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        return httpx.Response(200, text="ok", request=request)

    async def aclose(self) -> None:
        self.closed = True


def _fake_resolve(host: str, results: list[str]):
    """Return a getaddrinfo mock that maps the given host to fake IP results."""

    def _resolver(hostname, port, family=0, type_=0, proto=0, flags=0):
        if hostname == host:
            entries = []
            for ip in results:
                if ":" in ip:
                    entries.append((socket.AF_INET6, socket.SOCK_STREAM, proto, "", (ip, port or 0, 0, 0)))
                else:
                    entries.append((socket.AF_INET, socket.SOCK_STREAM, proto, "", (ip, port or 0)))
            return entries
        raise socket.gaierror(f"cannot resolve {hostname}")

    return _resolver


# ---------------------------------------------------------------------------
# construction
# ---------------------------------------------------------------------------

def test_transport_is_httpx_async_transport():
    t = PinnedDNSAsyncTransport()
    assert isinstance(t, httpx.AsyncBaseTransport)


def test_transport_accepts_keyword_args():
    inner = _RecordingTransport()
    t = PinnedDNSAsyncTransport(allow_loopback=True, inner=inner)
    assert t is not None
    # No public attribute assertions beyond what the upstream contract guarantees;
    # construction without errors is the contract.


def test_transport_defaults_to_real_inner_when_none():
    # Should not raise; an httpx.AsyncHTTPTransport is created by default.
    t = PinnedDNSAsyncTransport()
    assert isinstance(t, httpx.AsyncBaseTransport)


# ---------------------------------------------------------------------------
# handle_async_request — unsafe targets rejected before reaching inner
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ip,label", [
    ("127.0.0.1", "loopback"),
    ("10.0.0.1", "rfc1918_10"),
    ("169.254.169.254", "metadata"),
])
async def test_rejects_private_target(ip: str, label: str):
    inner = _RecordingTransport()
    transport = PinnedDNSAsyncTransport(inner=inner)
    request = httpx.Request("GET", "http://evil.com/secret")

    with patch("nanobot.security.network.socket.getaddrinfo", _fake_resolve("evil.com", [ip])):
        with pytest.raises(UnsafeHTTPRequestError):
            await transport.handle_async_request(request)

    # Inner transport must not have been called for an unsafe URL.
    assert inner.calls == [], f"inner transport should not be called for {label}"


async def test_rejects_unresolvable_hostname():
    inner = _RecordingTransport()
    transport = PinnedDNSAsyncTransport(inner=inner)
    request = httpx.Request("GET", "http://nonexistent.invalid/")

    def _raise(*args, **kwargs):
        raise socket.gaierror("no such host")

    with patch("nanobot.security.network.socket.getaddrinfo", _raise):
        with pytest.raises(UnsafeHTTPRequestError):
            await transport.handle_async_request(request)
    assert inner.calls == []


async def test_rejects_non_http_scheme():
    inner = _RecordingTransport()
    transport = PinnedDNSAsyncTransport(inner=inner)
    # httpx rejects ftp at Request construction; emulate with a malformed url
    # by constructing a custom request targeting a non-http scheme is impossible
    # via httpx.Request, so we instead verify via the file scheme which httpx
    # *does* allow at the Request level.
    request = httpx.Request("GET", "file:///etc/passwd")
    with pytest.raises(UnsafeHTTPRequestError):
        await transport.handle_async_request(request)
    assert inner.calls == []


# ---------------------------------------------------------------------------
# handle_async_request — safe targets forwarded to inner
# ---------------------------------------------------------------------------

async def test_safe_target_forwards_to_inner():
    inner = _RecordingTransport()
    transport = PinnedDNSAsyncTransport(inner=inner)
    request = httpx.Request("GET", "https://example.com/api/data")

    with patch("nanobot.security.network.socket.getaddrinfo", _fake_resolve("example.com", ["93.184.216.34"])):
        response = await transport.handle_async_request(request)

    assert response.status_code == 200
    assert len(inner.calls) == 1
    assert inner.calls[0].url == request.url


async def test_loopback_allowed_when_flag_true():
    """allow_loopback=True permits literal localhost (every addr is loopback)."""
    inner = _RecordingTransport()
    transport = PinnedDNSAsyncTransport(allow_loopback=True, inner=inner)
    request = httpx.Request("GET", "http://localhost:8765/health")

    with patch("nanobot.security.network.socket.getaddrinfo", _fake_resolve("localhost", ["127.0.0.1"])):
        response = await transport.handle_async_request(request)

    assert response.status_code == 200
    assert len(inner.calls) == 1


async def test_loopback_flag_does_not_allow_public_name_resolving_to_loopback():
    """A public DNS name that resolves to loopback must still be blocked."""
    inner = _RecordingTransport()
    transport = PinnedDNSAsyncTransport(allow_loopback=True, inner=inner)
    request = httpx.Request("GET", "http://example.com/secret")

    with patch("nanobot.security.network.socket.getaddrinfo", _fake_resolve("example.com", ["127.0.0.1"])):
        with pytest.raises(UnsafeHTTPRequestError):
            await transport.handle_async_request(request)
    assert inner.calls == []


# ---------------------------------------------------------------------------
# aclose
# ---------------------------------------------------------------------------

async def test_aclose_closes_inner():
    inner = _RecordingTransport()
    transport = PinnedDNSAsyncTransport(inner=inner)
    await transport.aclose()
    assert inner.closed is True


# ---------------------------------------------------------------------------
# pin_resolved_url_dns — the context manager used by the transport
# ---------------------------------------------------------------------------

def test_pin_resolved_url_dns_is_context_manager():
    # Must be usable as a context manager.
    with pin_resolved_url_dns("http://example.com/", ("93.184.216.34",)):
        pass


def test_pin_resolved_url_dns_overrides_getaddrinfo():
    """Inside the block, the pinned host resolves to the pinned IP."""
    original = socket.getaddrinfo
    try:
        with pin_resolved_url_dns("http://example.com/", ("93.184.216.34",)):
            infos = socket.getaddrinfo("example.com", None, socket.AF_UNSPEC, socket.SOCK_STREAM)
            ips = {info[4][0] for info in infos}
            assert ips == {"93.184.216.34"}, f"expected pinned IP, got {ips}"
    finally:
        assert socket.getaddrinfo is original


def test_pin_resolved_url_dns_noop_for_empty_ips():
    """Empty resolved_ips list is a no-op (real getaddrinfo still in place)."""
    with pin_resolved_url_dns("http://example.com/", ()):
        # socket.getaddrinfo remains the real implementation; just don't crash.
        pass
