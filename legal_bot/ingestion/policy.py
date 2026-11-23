# -*- coding: utf-8 -*-
"""Safety and resource limits for source discovery. No challenge bypass."""
from __future__ import annotations
from dataclasses import dataclass
from urllib.parse import urlparse

@dataclass(frozen=True)
class ConnectorPolicy:
    max_pages: int = 2
    max_candidates: int = 20
    request_timeout_seconds: int = 20
    min_request_interval_seconds: float = 3.0
    max_asset_bytes: int = 30 * 1024 * 1024
    user_agent: str = "MACHINA-LegalResearchBot/1.0 (polite public-source indexing)"
    allow_downloads: bool = False
    respect_robots_txt: bool = True
    stop_on_403: bool = True
    stop_on_429: bool = True
    stop_on_browser_challenge: bool = True


def host_allowed(url: str, allowed_hosts: set[str]) -> bool:
    """Exact-host allowlist; rejects credentials, non-HTTP schemes and lookalikes."""
    try:
        parsed = urlparse(url)
        return (parsed.scheme in {"http", "https"} and not parsed.username
                and not parsed.password and (parsed.hostname or "").lower() in
                {h.lower() for h in allowed_hosts})
    except (TypeError, ValueError):
        return False


def classify_http_response(status: int | None, content_type: str = "", body_prefix: str = "") -> str:
    body = (body_prefix or "").lower()
    ctype = (content_type or "").lower()
    if status in (403, 429):
        return "access_challenge" if status == 403 else "retry_later"
    if status is None or status >= 500:
        return "source_unavailable"
    if status < 200 or status >= 300:
        return "invalid_response"
    if "captcha" in body or "challenge-platform" in body or "checking your browser" in body:
        return "access_challenge"
    if "text/html" not in ctype and "application/pdf" not in ctype and "application/zip" not in ctype:
        return "invalid_response"
    return "ok"
