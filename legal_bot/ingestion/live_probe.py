# -*- coding: utf-8 -*-
"""Conservative, read-only connectivity probe for legal-source pages.

This module fetches robots.txt and one HTML page per source. It never fetches
PDF/ZIP assets, follows redirects outside the configured host allowlist, writes
to the staging registry, or changes the active legal corpus.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
from urllib.request import Request, urlopen
from typing import Callable

from .policy import ConnectorPolicy, classify_http_response, host_allowed


@dataclass
class ProbeResult:
    source_id: str
    page_url: str
    checked_at: str
    robots_status: str
    robots_http_status: int | None
    page_status: str
    page_http_status: int | None
    content_type: str | None
    final_url: str | None
    detail: str = ""

    def to_dict(self):
        return asdict(self)


def _read(url: str, policy: ConnectorPolicy, *, max_bytes: int = 256_000):
    request = Request(url, headers={"User-Agent": policy.user_agent, "Accept": "text/html,*/*;q=0.5"})
    try:
        with urlopen(request, timeout=policy.request_timeout_seconds) as response:
            final_url = response.geturl()
            original = urlparse(url)
            final = urlparse(final_url)
            if (final.scheme != "https" or not host_allowed(final_url, {original.hostname or ""})
                    or final.port not in (None, 443)):
                return None, None, None, final_url, "redirect_outside_allowed_https_origin"
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                return response.status, response.headers.get("Content-Type", ""), b"", final_url, "response_too_large"
            return response.status, response.headers.get("Content-Type", ""), body, final_url, ""
    except HTTPError as exc:
        return exc.code, exc.headers.get("Content-Type", ""), b"", url, str(exc)
    except (URLError, TimeoutError, OSError) as exc:
        return None, None, None, None, str(exc)


def probe_source(source: dict, policy: ConnectorPolicy | None = None, *, reader: Callable = _read) -> ProbeResult:
    policy = policy or ConnectorPolicy(allow_downloads=False, respect_robots_txt=True)
    page_url = source.get("pilot_url") or source.get("example_record_url") or source["base_url"]
    allowed = set(source.get("allowed_hosts", []))
    now = datetime.now(timezone.utc).isoformat()
    if not host_allowed(page_url, allowed):
        return ProbeResult(source["source_id"], page_url, now, "invalid_url", None,
                           "invalid_url", None, None, None, "page URL is outside source allowlist")

    robots_url = urljoin(source["base_url"], "/robots.txt")
    robots_status, robots_type, robots_body, robots_final, robots_error = reader(robots_url, policy)
    if robots_status == 404:
        robots_state, robots = "not_found", None
    elif robots_status is not None and 200 <= robots_status < 300 and robots_body is not None:
        robots_state = "read"
        parser = RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(robots_body.decode("utf-8", errors="replace").splitlines())
        robots = parser
    elif robots_status in (401, 403, 429) or robots_status is None or (robots_status and robots_status >= 500):
        return ProbeResult(source["source_id"], page_url, now, "unavailable_or_blocked", robots_status,
                           "not_attempted", None, None, robots_final, robots_error or "robots.txt could not be verified")
    else:
        return ProbeResult(source["source_id"], page_url, now, "invalid_response", robots_status,
                           "not_attempted", None, None, robots_final, robots_error)

    if robots is not None and not robots.can_fetch(policy.user_agent, page_url):
        return ProbeResult(source["source_id"], page_url, now, "disallowed", robots_status,
                           "not_attempted_robots_disallow", None, None, robots_final,
                           "robots.txt disallows this user-agent/page")

    status, ctype, body, final_url, error = reader(page_url, policy)
    classification = classify_http_response(status, ctype or "", (body or b"")[:4096].decode("utf-8", errors="ignore"))
    if error == "redirect_outside_allowed_host":
        classification = "invalid_response"
    return ProbeResult(source["source_id"], page_url, now, robots_state, robots_status,
                       classification, status, ctype, final_url, error)


def main() -> int:
    """Run a bounded probe for catalog sources; print JSON, write no files."""
    import json
    from pathlib import Path
    catalog_path = Path(__file__).with_name("SOURCE_CATALOG_V1.json")
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    policy = ConnectorPolicy(
        max_pages=1, max_candidates=0, request_timeout_seconds=12,
        min_request_interval_seconds=3.0, allow_downloads=False,
        respect_robots_txt=True,
    )
    results = []
    for index, source in enumerate(catalog.get("sources", [])):
        if index:
            import time
            time.sleep(policy.min_request_interval_seconds)
        results.append(probe_source(source, policy).to_dict())
    print(json.dumps({"probe_version": "1.0", "read_only": True,
                      "assets_downloaded": 0, "registry_written": False,
                      "active_corpus_modified": False, "results": results},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
