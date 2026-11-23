# -*- coding: utf-8 -*-
"""Phase 10.4.4: offline inspection of a saved Dotic record page.

Parses only supplied HTML. It never fetches pages or assets and never writes to
staging or active legal banks. Same-host HTTPS PDF links are reported as leads,
not authenticated official documents.
"""
from __future__ import annotations
import argparse
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

ALLOWED_HOSTS = {"dotic.ir", "www.dotic.ir"}
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

class _PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self._href = None
        self._text = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag.lower() == "a":
            self._href, self._text = attrs.get("href"), []
        elif tag.lower() in {"iframe", "embed", "object"}:
            src = attrs.get("src") or attrs.get("data")
            if src:
                self.links.append((src, attrs.get("title") or attrs.get("type") or ""))
    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)
    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            self.links.append((self._href, " ".join(" ".join(self._text).split())))
            self._href, self._text = None, []

def inspect_html(html: str, page_url: str) -> dict:
    parsed_page = urlparse(page_url)
    if parsed_page.scheme != "https" or parsed_page.hostname not in ALLOWED_HOSTS or parsed_page.username or parsed_page.password:
        raise ValueError("page_url must be credential-free HTTPS on an allowlisted Dotic host")
    parser = _PageParser(); parser.feed(html or "")
    assets, rejected = [], []
    seen = set()
    for href, label in parser.links:
        if not href:
            continue
        target = urljoin(page_url, href.strip())
        p = urlparse(target)
        if p.scheme != "https" or p.hostname not in ALLOWED_HOSTS or p.username or p.password:
            rejected.append({"href": href, "reason": "not_allowlisted_https_dotic_url"})
            continue
        if not p.path.lower().endswith(".pdf"):
            continue
        normalized = target.split("#", 1)[0]
        if normalized in seen:
            continue
        seen.add(normalized)
        assets.append({"url": normalized, "label": label, "kind": "pdf_link_candidate",
                       "authentication": "unverified", "downloaded": False,
                       "official_document_confirmed": False})
    text = (html or "").translate(_DIGITS)
    numbers = sorted(set(re.findall(r"(?:شماره|شمارهٔ)\s*[:：]?\s*([0-9]{2,})", text)))
    dates = sorted(set(re.findall(r"(?<!\d)(?:13|14)\d{2}/\d{1,2}/\d{1,2}(?!\d)", text)))
    return {
        "phase": "10.4.4", "page_url": page_url,
        "inspected_at": datetime.now(timezone.utc).isoformat(),
        "pdf_candidates": assets, "rejected_links": rejected,
        "metadata_hints": {"document_number_candidates": numbers, "date_candidates": dates},
        "limits": {"network_requests": 0, "pdf_downloads": 0, "active_bank_writes": 0,
                   "staging_writes": 0, "legal_authenticity_verified": False},
        "decision": "manual_review_required" if assets else "no_pdf_link_found_in_supplied_html",
        "warning": "A PDF link on a Dotic page is only a discovery lead; issuer, official publication, document identity and legal status require independent verification."
    }

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Offline Dotic detail-page HTML inspector")
    ap.add_argument("--html-file", required=True, help="Previously saved HTML file")
    ap.add_argument("--page-url", required=True, help="Original HTTPS Dotic page URL")
    ap.add_argument("--output", default="/data/ingestion_diagnostics/phase10_4_4_dotic_detail.json")
    args = ap.parse_args(argv)
    html = Path(args.html_file).read_text(encoding="utf-8", errors="replace")
    report = inspect_html(html, args.page_url)
    out = Path(args.output); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
