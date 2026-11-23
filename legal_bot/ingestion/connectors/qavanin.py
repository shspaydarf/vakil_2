# -*- coding: utf-8 -*-
"""Read-only, fixture-testable discovery parser for qavanin.ir.

This connector intentionally does not perform network I/O, solve browser challenges,
fetch PDFs, or write to any corpus. It parses saved Qavanin search-result HTML only.
Live access must be implemented separately after deployment access policy and robots
rules are verified.
"""
from __future__ import annotations

import html as html_lib
import re
from typing import Iterable
from urllib.parse import urlencode, urlparse

from .base import SourceConnector, SourceDefinition
from ..models import CandidateDocument


_TAGS = re.compile(r"<[^>]+>")
_IDS = re.compile(r"(?:[?&]|\b)IDS=(\d+)", re.IGNORECASE)
_ROW = re.compile(r"<tr\b([^>]*)>(.*?)</tr\s*>", re.IGNORECASE | re.DOTALL)
_CELL = re.compile(r"<td\b[^>]*>(.*?)</td\s*>", re.IGNORECASE | re.DOTALL)


def _plain(value: str) -> str:
    value = _TAGS.sub(" ", value or "")
    value = html_lib.unescape(value)
    return " ".join(value.split())


def _is_qavanin_host(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return (parsed.scheme == "https" and parsed.hostname in {"qavanin.ir", "www.qavanin.ir"}
                and not parsed.username and not parsed.password and parsed.port in (None, 443))
    except (TypeError, ValueError):
        return False


class QavaninConnector(SourceConnector):
    """Parse Qavanin result rows into unverified discovery candidates."""

    definition = SourceDefinition(
        source_id="qavanin_national",
        source_name="سامانه ملی قوانین و مقررات جمهوری اسلامی ایران (Qavanin)",
        base_url="https://qavanin.ir/",
        allowed_hosts=frozenset({"qavanin.ir", "www.qavanin.ir"}),
        source_role="official_registry_candidate_unverified",
    )

    allowed_categories = frozenset({
        "laws", "regulations_and_bylaws", "supreme_court_unity_rulings",
        "administrative_justice_general_assembly_rulings", "judiciary_advisory_opinions",
    })
    _document_types = {
        "laws": "law_candidate",
        "regulations_and_bylaws": "regulation_candidate",
        "supreme_court_unity_rulings": "supreme_court_ruling_candidate",
        "administrative_justice_general_assembly_rulings": "administrative_court_ruling_candidate",
        "judiciary_advisory_opinions": "advisory_opinion_candidate",
    }

    @staticmethod
    def build_search_url(query: str, *, page: int = 1, in_text: bool = False,
                         limit: int = 25) -> str:
        """Build a conservative Qavanin search URL; does not send a request."""
        query = " ".join(str(query or "").split())
        if not query:
            raise ValueError("عبارت جست‌وجو نمی‌تواند خالی باشد")
        if len(query) > 200:
            raise ValueError("عبارت جست‌وجو بیش از حد طولانی است")
        if isinstance(page, bool) or not isinstance(page, int) or not 1 <= page <= 10000:
            raise ValueError("شماره صفحه باید بین ۱ تا ۱۰۰۰۰ باشد")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("تعداد نتایج باید بین ۱ تا ۱۰۰ باشد")
        params = {
            "CAPTION": query,
            "IsTextSearch" if in_text else "IsTitleSearch": "true",
            "SeachTextType": "1",
            "size": str(25 if limit <= 25 else 50 if limit <= 50 else 100),
            "PageNumber": str(page),
            "SortColumn": "APPROVEDATE",
            "SortDesc": "True",
        }
        return "https://qavanin.ir/?" + urlencode(params)

    @staticmethod
    def document_url(record_id: str) -> str:
        value = str(record_id or "").strip()
        if not value.isdigit() or len(value) > 24:
            raise ValueError("شناسه سند Qavanin معتبر نیست")
        return f"https://qavanin.ir/Law/TreeText/?IDS={value}"

    def discover_from_html(self, html: str, page_url: str, *, category: str) -> Iterable[CandidateDocument]:
        if category not in self.allowed_categories or not _is_qavanin_host(page_url):
            return []
        body = html or ""
        lowered = body.lower()
        # Fail closed: do not parse challenge/error pages as legal search results.
        if "__arcsjs" in lowered or "captcha" in lowered or "checking your browser" in lowered:
            return []
        output: list[CandidateDocument] = []
        seen: set[str] = set()
        for match in _ROW.finditer(body):
            attrs, row_html = match.groups()
            id_match = _IDS.search(row_html)
            cells = _CELL.findall(row_html)
            if not id_match or len(cells) < 4:
                continue
            record_id = id_match.group(1)
            if record_id in seen:
                continue
            seen.add(record_id)
            title = _plain(cells[1])
            approved = _plain(cells[2]) or None
            approver = _plain(cells[3]) or None
            if not title:
                continue
            is_repealed = bool(re.search(r"(?:^|\s)red(?:\s|$)", attrs, re.IGNORECASE))
            notes = (
                "نامزد کشف‌شده از صفحه نتایج Qavanin؛ این اتصالگر فقط HTML ذخیره‌شده را پردازش می‌کند. "
                "وضعیت نمایش‌داده‌شده در نتیجه جست‌وجو، اصالت انتشار و اعتبار حقوقی فعلی را به‌تنهایی اثبات نمی‌کند. "
                "متن کامل، اصلاحات، تاریخچه وضعیت و منبع انتشار باید جداگانه تطبیق و بازبینی شوند؛ "
                "ورود به بانک فعال مجاز نیست."
            )
            if is_repealed:
                notes += " نتیجه منبع با نشان منسوخ‌شده نمایش داده شده و باید با جزئیات سند تطبیق شود."
            output.append(CandidateDocument(
                source_id=self.definition.source_id,
                source_name=self.definition.source_name,
                source_role=self.definition.source_role,
                document_type=self._document_types[category],
                title=title,
                page_url=self.document_url(record_id),
                asset_url=None,
                source_record_id=record_id,
                issuer=approver,
                document_date=approved,
                notes=notes,
            ))
            if len(output) >= self.policy.max_candidates:
                break
        return output
