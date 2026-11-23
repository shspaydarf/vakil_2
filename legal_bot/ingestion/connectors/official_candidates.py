# -*- coding: utf-8 -*-
"""Conservative fixture-testable parsers for additional Iranian official-source candidates.

These adapters parse supplied HTML only. They do not fetch pages, download assets,
verify legal authority, infer current validity, or write to any bank. A source's
presence here is not proof that its live endpoints or publication workflow work.
"""
from __future__ import annotations
from html.parser import HTMLParser
from typing import Iterable
from urllib.parse import urljoin, urlparse
import re

from .base import SourceConnector, SourceDefinition
from ..models import CandidateDocument
from ..policy import host_allowed


class _Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items: list[tuple[str, str]] = []
        self.href: str | None = None
        self.text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            self.href = dict(attrs).get("href")
            self.text = []

    def handle_data(self, data):
        if self.href is not None:
            self.text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self.href is not None:
            self.items.append((self.href, " ".join(" ".join(self.text).split())))
            self.href, self.text = None, []


_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_YEAR = re.compile(r"(?<!\d)(13\d{2}|14\d{2})(?!\d)")


class _OfficialCandidateConnector(SourceConnector):
    allowed_categories: frozenset[str] = frozenset()
    issuer_name = ""
    doc_type = ""
    path_hints: tuple[str, ...] = ()

    def discover_from_html(self, html: str, page_url: str, *, category: str) -> Iterable[CandidateDocument]:
        if category not in self.allowed_categories or not host_allowed(page_url, set(self.definition.allowed_hosts)):
            return []
        parser = _Links()
        parser.feed(html or "")
        output: list[CandidateDocument] = []
        seen: set[str] = set()
        for href, label in parser.items:
            if not href:
                continue
            target = urljoin(page_url, href.strip())
            if not host_allowed(target, set(self.definition.allowed_hosts)):
                continue
            parsed = urlparse(target)
            path = parsed.path.lower()
            text = (label + " " + path).translate(_DIGITS).lower()
            is_pdf = path.endswith(".pdf")
            looks_record = any(hint in text for hint in self.path_hints)
            if not (is_pdf or looks_record) or target in seen:
                continue
            seen.add(target)
            years = _YEAR.findall(text)
            title = label or ("پیوست PDF سند حقوقی" if is_pdf else "صفحه رکورد سند حقوقی")
            output.append(CandidateDocument(
                source_id=self.definition.source_id,
                source_name=self.definition.source_name,
                source_role=self.definition.source_role,
                document_type=self.doc_type + ("_pdf" if is_pdf else "_record"),
                title=title,
                page_url=page_url,
                asset_url=target if is_pdf else None,
                source_record_id=None,
                issuer=self.issuer_name,
                document_date=years[0] if len(years) == 1 else None,
                notes=("کشف اولیه از دامنه رسمیِ کاندید؛ اتصال زنده، هویت سند، انتشار رسمی و اعتبار حقوقی "
                       "هنوز مستقل تأیید نشده‌اند. این رکورد مجوز ورود به بانک فعال نیست."),
            ))
            if len(output) >= self.policy.max_candidates:
                break
        return output


class DoticRegulationsConnector(_OfficialCandidateConnector):
    definition = SourceDefinition("national_regulations", "سامانه ملی قوانین و مقررات کشور", "https://dotic.ir/",
                                  frozenset({"dotic.ir", "www.dotic.ir"}), "official_registry_candidate_unverified")
    allowed_categories = frozenset({"laws", "regulations_and_bylaws", "supreme_court_unity_rulings",
                                    "administrative_justice_general_assembly_rulings", "judiciary_advisory_opinions"})
    issuer_name = "مرجع صادرکننده مندرج در سند"
    doc_type = "national_regulation"
    path_hints = ("law", "regulation", "rule", "document", "قانون", "مقرره", "آیین", "news/")

    def discover_from_html(self, html: str, page_url: str, *, category: str) -> Iterable[CandidateDocument]:
        """Parse Dotic /news/{id} discovery records observed on its public homepage.

        This creates discovery candidates only. The linked news page may describe a
        decision or a monthly advisory-opinion collection without exposing the PDF
        asset as a normal anchor; a separate detail/asset resolution step is required.
        """
        if category not in self.allowed_categories or not host_allowed(page_url, set(self.definition.allowed_hosts)):
            return []
        # Preserve direct PDF discovery for legislation and regulations.
        output: list[CandidateDocument] = []
        if category in {"laws", "regulations_and_bylaws"}:
            output.extend(super().discover_from_html(html, page_url, category=category))
        parser = _Links()
        parser.feed(html or "")
        seen: set[str] = {item.asset_url for item in output if item.asset_url}
        for href, label in parser.items:
            if not href:
                continue
            target = urljoin(page_url, href.strip())
            if not host_allowed(target, set(self.definition.allowed_hosts)):
                continue
            parsed = urlparse(target)
            match = re.fullmatch(r"/news/(\d+)/?", parsed.path)
            if not match or target in seen:
                continue
            title = label.strip()
            normalized = title.translate(_DIGITS)
            if category == "judiciary_advisory_opinions" and not ("نظریه مشورتی" in title or "نظریات مشورتی" in title):
                continue
            if category == "supreme_court_unity_rulings" and not ("وحدت رویه" in title):
                continue
            if category == "administrative_justice_general_assembly_rulings" and not ("هیات عمومی دیوان عدالت" in title or "هیأت عمومی دیوان عدالت" in title):
                continue
            if category == "laws" and not ("قانون" in title):
                continue
            if category == "regulations_and_bylaws" and not any(x in title for x in ("آیین نامه", "آیین‌نامه", "تصویبنامه", "تصویب‌نامه", "مقرره")):
                continue
            seen.add(target)
            kind = {
                "laws": "law_record",
                "regulations_and_bylaws": "regulation_record",
                "supreme_court_unity_rulings": "supreme_court_ruling_record",
                "administrative_justice_general_assembly_rulings": "administrative_court_ruling_record",
                "judiciary_advisory_opinions": "advisory_opinion_collection_record",
            }[category]
            output.append(CandidateDocument(
                source_id=self.definition.source_id, source_name=self.definition.source_name,
                source_role=self.definition.source_role, document_type=kind, title=title,
                page_url=target, asset_url=None, source_record_id=match.group(1),
                issuer=self.issuer_name, notes=(
                    "رکورد کشف‌شده از صفحه عمومی dotic.ir؛ صفحه خبر به‌تنهایی سند اصلی یا فایل پیوست را اثبات نمی‌کند. "
                    "حل پیوند متن کامل، دریافت PDF، اصالت سند و وضعیت حقوقی باید جداگانه بررسی شود؛ ورود به بانک فعال مجاز نیست."
                )))
            if len(output) >= self.policy.max_candidates:
                break
        return output


class OfficialGazetteConnector(_OfficialCandidateConnector):
    definition = SourceDefinition("official_gazette", "روزنامه رسمی جمهوری اسلامی ایران", "https://rrk.ir/",
                                  frozenset({"rrk.ir", "www.rrk.ir"}), "official_publication_candidate_unverified")
    allowed_categories = frozenset({"laws", "regulations_and_bylaws", "official_publications"})
    issuer_name = "مرجع صادرکننده مندرج در آگهی"
    doc_type = "official_gazette_publication"
    path_hints = ("law", "notice", "newspaper", "publication", "قانون", "آگهی", "روزنامه")


class JudiciaryPortalConnector(_OfficialCandidateConnector):
    definition = SourceDefinition("eadil_portal", "درگاه ملی قوه قضاییه", "https://eadil.com/",
                                  frozenset({"eadil.com", "www.eadil.com"}), "judiciary_portal_candidate_unverified")
    allowed_categories = frozenset({"supreme_court_unity_rulings", "administrative_justice_general_assembly_rulings",
                                    "judiciary_advisory_opinions", "judiciary_circulars"})
    issuer_name = "مرجع قضایی مندرج در سند"
    doc_type = "judiciary_document"
    path_hints = ("ruling", "opinion", "advisory", "unity", "decision", "رأی", "رای", "نظریه", "وحدت")
