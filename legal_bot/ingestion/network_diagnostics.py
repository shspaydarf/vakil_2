# -*- coding: utf-8 -*-
"""Read-only diagnostics for approved source connectivity.

This module never changes DNS settings, uses alternate resolvers, follows redirects,
uses proxies, or bypasses access controls. It stops at the first failed layer.
"""
from __future__ import annotations

import ipaddress
import socket
import ssl
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Iterable
from urllib.parse import urlparse


@dataclass(frozen=True)
class HostDiagnostic:
    host: str
    status: str
    resolved_addresses: tuple[str, ...] = ()
    detail: str = ""
    checked_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def diagnose_host(url: str, *, timeout: float = 4.0) -> HostDiagnostic:
    """Check system DNS then a standard verified TLS handshake; make no HTTP request."""
    parsed = urlparse(url)
    now = datetime.now(timezone.utc).isoformat()
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return HostDiagnostic(parsed.hostname or "", "rejected_url", detail="Only credential-free HTTPS URLs are accepted", checked_at=now)
    host = parsed.hostname.lower().rstrip(".")
    port = parsed.port or 443
    if port != 443:
        return HostDiagnostic(host, "rejected_port", detail="Only standard HTTPS port 443 is permitted", checked_at=now)
    try:
        records = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        addresses = tuple(sorted({record[4][0] for record in records}))
    except socket.gaierror as exc:
        return HostDiagnostic(host, "dns_failed", detail=f"System resolver failed: {exc}", checked_at=now)
    except OSError as exc:
        return HostDiagnostic(host, "dns_error", detail=f"System resolver error: {exc}", checked_at=now)
    if not addresses:
        return HostDiagnostic(host, "dns_empty", detail="System resolver returned no addresses", checked_at=now)
    if any(not ipaddress.ip_address(address).is_global for address in addresses):
        return HostDiagnostic(host, "non_global_address_rejected", addresses,
                              "At least one DNS result is not globally routable", now)
    try:
        # Pin the connection to a system-resolver result; retain hostname for TLS SNI.
        family, socktype, proto, _, sockaddr = records[0]
        raw = socket.socket(family, socktype, proto)
        raw.settimeout(timeout)
        raw.connect(sockaddr)
        try:
            with ssl.create_default_context().wrap_socket(raw, server_hostname=host) as tls:
                cert = tls.getpeercert()
                if not cert:
                    return HostDiagnostic(host, "tls_unverified", addresses, "TLS peer certificate unavailable", now)
        finally:
            # wrap_socket owns/closes raw after successful wrapping; close is idempotent.
            raw.close()
    except ssl.SSLCertVerificationError as exc:
        return HostDiagnostic(host, "tls_certificate_failed", addresses, str(exc), now)
    except (ssl.SSLError, OSError, TimeoutError) as exc:
        return HostDiagnostic(host, "tcp_or_tls_failed", addresses, str(exc), now)
    return HostDiagnostic(host, "tls_ok_http_not_tested", addresses, "Verified TLS handshake succeeded; no HTTP request was sent", now)


def diagnose_sources(sources: Iterable[dict], *, timeout: float = 4.0) -> list[dict]:
    """Run bounded diagnostics against source registry URLs."""
    results = []
    for source in sources:
        result = diagnose_host(str(source.get("url", "")), timeout=timeout).to_dict()
        result["source_id"] = source.get("source_id", "")
        results.append(result)
    return results
