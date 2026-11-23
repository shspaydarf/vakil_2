# -*- coding: utf-8 -*-
"""Read-only HTML discovery connector for Ekhtebar's Supreme Court unity-ruling archive.

This parser consumes saved HTML only. It does not make network requests, download
assets, bypass challenges, or write to the active legal corpus.
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
        self._href: str | None = None
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() == "a":
            self._href = dict(attrs).get("href")
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href is not None:
            self.anchors.append((self._href, " ".join(" ".join(self._parts).split())))
            self._href = None
            self._parts = []


_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_YEAR_RE = re.compile(r"(?<!\d)(13\d{2}|14\d{2})(?!\d)")


class EkhtebarUnityRulingsConnector(SourceConnector):
    definition = SourceDefinition(
        source_id="ekhtebar",
        source_name="پایگاه خبری اختبار",
        base_url="https://www.ekhtebar.ir/",
        allowed_hosts=frozenset({"www.ekhtebar.ir", "ekhtebar.ir"}),
        source_role="secondary_discovery",
    )

    def discover_from_html(self, html: str, page_url: str, *, category: str) -> Iterable[CandidateDocument]:
        if category != "supreme_court_unity_rulings":
            return []
        if not host_allowed(page_url, set(self.definition.allowed_hosts)):
            return []

        parser = _AnchorCollector()
        parser.feed(html or "")
        results: list[CandidateDocument] = []
        seen: set[str] = set()
        for href, label in parser.anchors:
            if not href or not label:
                continue
            asset_url = urljoin(page_url, href.strip())
            if not host_allowed(asset_url, set(self.definition.allowed_hosts)):
                continue
            path = urlparse(asset_url).path.lower()
            if not (path.endswith(".pdf") or path.endswith(".zip")):
                continue
            if asset_url in seen:
                continue
            seen.add(asset_url)

            title = label.strip()
            normalized = title.translate(_PERSIAN_DIGITS)
            year_matches = _YEAR_RE.findall(normalized)
            doc_type = "supreme_court_ruling_archive_bundle" if path.endswith(".zip") else "supreme_court_ruling_collection"
            notes = "Archive asset discovered from Ekhtebar; secondary discovery source, not proof of official authenticity."
            if len(year_matches) == 1:
                notes += f" Parsed year hint: {year_matches[0]}."
            results.append(CandidateDocument(
                source_id=self.definition.source_id,
                source_name=self.definition.source_name,
                source_role=self.definition.source_role,
                document_type=doc_type,
                title=title,
                page_url=page_url,
                asset_url=asset_url,
                issuer="دیوان عالی کشور",
                document_date=year_matches[0] if len(year_matches) == 1 else None,
                notes=notes,
            ))
            if len(results) >= self.policy.max_candidates:
                break
        return results
