# -*- coding: utf-8 -*-
"""Phase 4.2: conservative validation of legal-document identity metadata.

This is a screening aid. It does not authenticate an instrument, resolve legal
competence, or infer missing metadata as fact.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any, Mapping

VALIDATOR_VERSION = "4.2.0"
_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


@dataclass(frozen=True)
class MetadataFinding:
    code: str
    severity: str
    field: str
    message: str


@dataclass
class MetadataValidationReport:
    validator_version: str
    document_type: str | None
    overall_status: str = "needs_review"
    checks: dict[str, str] = field(default_factory=dict)
    normalized_metadata: dict[str, str | None] = field(default_factory=dict)
    findings: list[MetadataFinding] = field(default_factory=list)
    legal_authenticity: str = "not_proven"

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["findings"] = [asdict(x) for x in self.findings]
        return result


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).translate(_DIGIT_MAP)
    text = text.replace("ي", "ی").replace("ك", "ک")
    text = re.sub(r"[\u200c\u200e\u200f\u202a-\u202e]", "", text)
    return re.sub(r"\s+", " ", text).strip(" \t\r\n،,؛;")


def _key(value: Any) -> str:
    return re.sub(r"[\s\-_/]+", "", _norm(value)).casefold()


def _parse_date(value: Any) -> tuple[str, tuple[int, int, int] | None, str | None]:
    raw = _norm(value)
    if not raw:
        return "missing", None, None
    # Accept ISO and common slash/dash/dot forms, without guessing ambiguous order.
    match = re.fullmatch(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", raw)
    if not match:
        return "unrecognized_format", None, None
    y, m, d = map(int, match.groups())
    if 1200 <= y <= 1499:  # likely Solar Hijri; validate ranges only, no calendar conversion
        if not (1 <= m <= 12 and 1 <= d <= (30 if m == 12 else 31)):
            return "invalid_date", None, "jalali"
        return "valid", (y, m, d), "jalali"
    try:
        date(y, m, d)
    except ValueError:
        return "invalid_date", None, "gregorian"
    return "valid", (y, m, d), "gregorian"


def _add(report: MetadataValidationReport, code: str, severity: str, field_name: str, message: str) -> None:
    report.findings.append(MetadataFinding(code, severity, field_name, message))


def _first(*sources: Mapping[str, Any], key: str) -> Any:
    for source in sources:
        value = source.get(key)
        if value is not None and str(value).strip():
            return value
    return None


def validate_document_metadata(
    candidate: Mapping[str, Any],
    extracted_metadata: Mapping[str, Any] | None = None,
    source_page_metadata: Mapping[str, Any] | None = None,
) -> MetadataValidationReport:
    """Compare candidate, extracted and source-page metadata conservatively.

    Priority is not treated as truth: all supplied values are compared. Missing
    fields remain missing; no issuer/date/number is synthesized.
    """
    extracted = extracted_metadata or {}
    source_page = source_page_metadata or {}
    sources = (candidate, extracted, source_page)
    doc_type = _first(*sources, key="document_type") or _first(*sources, key="type")
    report = MetadataValidationReport(VALIDATOR_VERSION, _norm(doc_type) or None)

    # Type and authority compatibility is deliberately advisory and coarse.
    type_text = _key(doc_type)
    issuer = _first(*sources, key="issuer") or _first(*sources, key="issuing_authority")
    issuer_text = _norm(issuer)
    report.normalized_metadata["document_type"] = _norm(doc_type) or None
    report.normalized_metadata["issuer"] = issuer_text or None

    authority_groups = {
        "parliament": ("مجلس", "مجلسشورایاسلامی", "قانونگذاری"),
        "government": ("هیئتمدیران", "دولت", "هیئتنمایندگان", "وزیران"),
        "judiciary": ("قوهقضاییه", "دیوانعالی", "دیوانعدالتاداری", "دادستانیکل"),
        "ministry": ("وزارت", "وزیر"),
    }
    issuer_group = next((group for group, terms in authority_groups.items()
                         if any(_key(term) in _key(issuer_text) for term in terms)), None)
    type_group = None
    if any(_key(term) in type_text for term in ("قانون", "مصوبه مجلس", "طرح", "لایحه")):
        type_group = "parliament"
    elif any(_key(term) in type_text for term in ("آییننامه", "تصویبنامه", "تصویب نامه", "مقرره دولت")):
        type_group = "government"
    elif any(_key(term) in type_text for term in ("بخشنامه قضایی", "دستورالعمل قضایی", "رأی وحدت رویه", "رای وحدت رویه")):
        type_group = "judiciary"
    elif any(_key(term) in type_text for term in ("بخشنامه وزارت", "دستورالعمل وزارت")):
        type_group = "ministry"
    if issuer and doc_type and issuer_group and type_group:
        if issuer_group == type_group or (type_group == "government" and issuer_group == "ministry"):
            report.checks["issuer_type_compatibility"] = "plausible_not_verified"
        else:
            report.checks["issuer_type_compatibility"] = "review_required"
            _add(report, "ISSUER_TYPE_POTENTIAL_CONFLICT", "medium", "issuer",
                 "مرجع ثبت‌شده با نوع سند از نظر الگوی اولیه سازگار به نظر نمی‌رسد؛ صلاحیت قانونی باید انسانی بررسی شود.")
    else:
        report.checks["issuer_type_compatibility"] = "insufficient_metadata"
        _add(report, "ISSUER_TYPE_NOT_ASSESSABLE", "info", "issuer",
             "برای ارزیابی اولیه تناسب مرجع و نوع سند، اطلاعات کافی یا قابل دسته‌بندی وجود ندارد.")

    # Identity fields: compare all available sources, never silently select conflicting values.
    fields = ("title", "issuer", "document_number")
    for name in fields:
        values = [_norm(src.get(name) or (src.get("issuing_authority") if name == "issuer" else "")) for src in sources]
        present = [v for v in values if v]
        report.normalized_metadata[name] = present[0] if present else None
        if not present:
            report.checks[f"{name}_presence"] = "missing"
            _add(report, f"MISSING_{name.upper()}", "medium", name, f"فیلد {name} در داده‌های ارائه‌شده موجود نیست.")
        elif len({_key(v) for v in present}) > 1:
            report.checks[f"{name}_agreement"] = "conflict"
            _add(report, f"{name.upper()}_CONFLICT", "high", name,
                 f"مقادیر {name} در اطلاعات کشف، متن استخراج‌شده یا صفحه منبع با هم اختلاف دارند.")
        else:
            report.checks[f"{name}_agreement"] = "consistent_across_available_sources"

    number = _first(*sources, key="document_number")
    if number:
        normalized_number = _norm(number)
        # Number may contain Persian letters, slash and hyphen; reject only control chars / implausible length.
        if len(normalized_number) > 100 or any(unicodedata.category(ch) == "Cc" for ch in normalized_number):
            report.checks["document_number_format"] = "suspicious"
            _add(report, "DOCUMENT_NUMBER_SUSPICIOUS", "medium", "document_number", "قالب شماره سند غیرعادی است و باید بازبینی شود.")
        else:
            report.checks["document_number_format"] = "accepted_for_review"

    date_fields = ("enactment_date", "notification_date", "publication_date", "document_date")
    parsed: dict[str, tuple[tuple[int, int, int], str]] = {}
    for name in date_fields:
        values = [_norm(src.get(name)) for src in sources if _norm(src.get(name))]
        if name == "document_date" and not values:
            values = [_norm(src.get("date")) for src in sources if _norm(src.get("date"))]
        if not values:
            report.normalized_metadata[name] = None
            report.checks[f"{name}_format"] = "missing"
            continue
        states = [_parse_date(value) for value in values]
        if any(state[0] == "invalid_date" for state in states):
            report.checks[f"{name}_format"] = "invalid"
            _add(report, "INVALID_DATE", "high", name, f"تاریخ {name} از نظر قالب تقویمی معتبر نیست.")
        elif any(state[0] != "valid" for state in states):
            report.checks[f"{name}_format"] = "unrecognized"
            _add(report, "UNRECOGNIZED_DATE_FORMAT", "medium", name, f"قالب تاریخ {name} قابل تفسیر مطمئن نیست.")
        else:
            calendars = {state[2] for state in states}
            if len(calendars) > 1:
                report.checks[f"{name}_format"] = "calendar_mismatch"
                _add(report, "DATE_CALENDAR_MISMATCH", "medium", name, f"تقویم تاریخ‌های {name} یکسان نیست.")
            elif len({state[1] for state in states}) > 1:
                report.checks[f"{name}_agreement"] = "conflict"
                _add(report, "DATE_VALUE_CONFLICT", "high", name, f"مقادیر تاریخ {name} در منابع مختلف یکسان نیست.")
            else:
                report.checks[f"{name}_format"] = "valid_format_only"
                report.checks[f"{name}_agreement"] = "consistent_across_available_sources"
                parsed[name] = (states[0][1], states[0][2])
        report.normalized_metadata[name] = values[0]

    # Chronology only when dates are in the same calendar and both are parseable.
    for earlier, later in (("enactment_date", "notification_date"), ("notification_date", "publication_date"),
                           ("enactment_date", "publication_date")):
        if earlier in parsed and later in parsed:
            a, ca = parsed[earlier]
            b, cb = parsed[later]
            if ca == cb and a > b:
                report.checks[f"chronology_{earlier}_{later}"] = "review_required"
                _add(report, "DATE_CHRONOLOGY_REVIEW", "medium", later,
                     f"ترتیب {earlier} و {later} غیرمنتظره است؛ احتمال تفاوت تقویم یا خطای استخراج بررسی شود.")

    high = any(f.severity in {"high", "critical"} for f in report.findings)
    medium = any(f.severity == "medium" for f in report.findings)
    report.overall_status = "conflict_detected" if high else "needs_human_review" if medium else "screening_passed"
    # Even a clean metadata screen never proves legal authenticity.
    report.legal_authenticity = "not_proven"
    return report
