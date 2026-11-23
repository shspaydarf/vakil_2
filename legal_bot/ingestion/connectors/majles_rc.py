# -*- coding: utf-8 -*-
"""Fixture-testable, read-only discovery parser for the Majles Research Center law archive.

This connector only identifies law record pages and direct PDF links already present
in supplied HTML. It performs no network I/O, downloads, legal-status decisions or
writes to the active corpus.
"""
from __future__ import annotations

from html.parser import HTMLParser
import re
from urllib.parse import urljoin, urlparse
from typing import Iterable

from .base import SourceConnector, SourceDefinition
from ..models import CandidateDocument
from ..policy import host_allowed


class _AnchorCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.anchors: list[tuple[str, str]] = []
        self.href: str | None = None
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            self.href = dict(attrs).get("href")
            self.parts = []

    def handle_data(self, data):
        if self.href is not None:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self.href is not None:
            self.anchors.append((self.href, " ".join(" ".join(self.parts).split())))
            self.href, self.parts = None, []


_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_ID_RE = re.compile(r"/(?:fa/)?law/(?:show|print_version)/(\d+)(?:/|$)", re.I)
_YEAR_RE = re.compile(r"(?<!\d)(13\d{2}|14\d{2})(?!\d)")


class MajlesResearchCenterConnector(SourceConnector):
    definition = SourceDefinition(
        source_id="majles_rc",
        source_name="مرکز پژوهش‌های مجلس شورای اسلامی",
        base_url="https://rc.majlis.ir/fa/law",
        allowed_hosts=frozenset({"rc.majlis.ir"}),
        source_role="preferred_parliamentary_discovery",
    )

    def discover_from_html(self, html: str, page_url: str, *, category: str) -> Iterable[CandidateDocument]:
        if category not in {"parliamentary_laws", "laws"}:
            return []
        if not host_allowed(page_url, set(self.definition.allowed_hosts)):
            return []
        parser = _AnchorCollector()
        parser.feed(html or "")
        results: list[CandidateDocument] = []
        seen: set[str] = set()
        for href, label in parser.anchors:
            if not href:
                continue
            url = urljoin(page_url, href.strip())
            if not host_allowed(url, set(self.definition.allowed_hosts)):
                continue
            path = urlparse(url).path
            match = _ID_RE.search(path)
            is_pdf = path.lower().endswith(".pdf")
            if not match and not is_pdf:
                continue
            key = url.split("#", 1)[0]
            if key in seen:
                continue
            seen.add(key)
            normalized = label.translate(_DIGITS).strip()
            years = _YEAR_RE.findall(normalized)
            is_record = bool(match)
            results.append(CandidateDocument(
                source_id=self.definition.source_id,
                source_name=self.definition.source_name,
                source_role=self.definition.source_role,
                document_type="parliamentary_law_record" if is_record else "parliamentary_law_pdf",
                title=normalized or (f"سند قانونی شماره {match.group(1)}" if match else "پیوست PDF قانون"),
                page_url=page_url,
                asset_url=url if is_pdf else None,
                source_record_id=match.group(1) if match else None,
                issuer="مجلس شورای اسلامی",
                document_date=years[0] if len(years) == 1 else None,
                notes="کشف اولیه از منبع مجلس؛ این رکورد به‌تنهایی اصالت، تصویب، انتشار یا اعتبار فعلی قانون را اثبات نمی‌کند.",
            ))
            if len(results) >= self.policy.max_candidates:
                break
        return results
