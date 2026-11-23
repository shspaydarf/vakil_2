# -*- coding: utf-8 -*-
"""Phase 8.2: record bounded live-source probe evidence; no downloads or writes to legal banks."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Any
from urllib.parse import urlparse

@dataclass(frozen=True)
class ProbeEvidence:
    source_id: str
    source_role: str
    outcome: str
    url: str
    detail: str
    evidence_origin: str
    document_pages: int | None = None


def build_phase8_2_report() -> dict[str, Any]:
    evidence = [
        ProbeEvidence(
            source_id="majles_rc", source_role="official_primary_candidate",
            outcome="http_502_from_chat_web_probe",
            url="https://rc.majlis.ir/fa/law/show/93849",
            detail="بازکردن مستقیم صفحه در محیط بررسی وب با 502 Bad Gateway ناموفق بود. این نتیجه وضعیت شبکه یا مرورگر استقرار MACHINA را تعیین نمی‌کند. مسیر سه‌مرحله‌ای چاپ فقط بر اساس تصاویر و توضیح کاربر شناخته شده است.",
            evidence_origin="chat_web_open_attempt_and_user_screenshots",
        ),
        ProbeEvidence(
            source_id="ekhtebar", source_role="secondary_reference_only",
            outcome="listing_page_readable_pdf_link_confirmed",
            url="https://www.ekhtebar.ir/قوانین/",
            detail="صفحه فهرست قوانین در محیط بررسی وب خوانده شد؛ جدول عنوان/سال/لینک PDF دارد. برای نمونه، لینک PDF قانون کاهش مجازات حبس تعزیری باز شد و محتوای PDF هفت‌صفحه‌ای قابل مشاهده و استخراج متنی بود. این نمونه سند پایلوت مجلس نیست و فقط مسیر فنی PDF اختبار را نشان می‌دهد.",
            evidence_origin="chat_web_open_and_link_click",
            document_pages=7,
        ),
        ProbeEvidence(
            source_id="ekhtebar_pdf_sample", source_role="secondary_sample_not_official_primary",
            outcome="pdf_opened_and_text_visible",
            url="https://www.ekhtebar.ir/wp-content/uploads/2020/06/قانون-کاهش-مجازات-حبس-تعزیری-2.pdf",
            detail="PDF نمونه در محیط وب باز شد؛ هفت صفحه گزارش شد و متن صفحات قابل مشاهده بود. دریافت فایل توسط runtime پروژه، ذخیره staging، OCR محلی و تطبیق حقوقی با نسخه رسمی انجام نشد.",
            evidence_origin="chat_web_pdf_open",
            document_pages=7,
        ),
    ]
    report: dict[str, Any] = {
        "phase": "8.2",
        "purpose": "bounded_live_source_probe",
        "evidence": [asdict(x) for x in evidence],
        "findings": {
            "ekhtebar_listing_and_direct_pdf_route_observed": True,
            "majles_live_route_confirmed": False,
            "ekhtebar_is_secondary_only": True,
            "pilot_document_93849_downloaded": False,
            "project_runtime_connectivity_proven": False,
            "local_pdf_downloaded": False,
            "ocr_run": False,
            "staging_written": False,
            "active_bank_modified": False,
            "legal_validity_assessed": False,
        },
        "next_gate": "8.3_download_one_authorized_sample_and_validate_without_active_bank_import",
    }
    canonical = json.dumps(report, ensure_ascii=False, sort_keys=True).encode("utf-8")
    report["report_sha256"] = sha256(canonical).hexdigest()
    return report


def validate_phase8_2_report(report: dict[str, Any]) -> bool:
    if report.get("phase") != "8.2" or report.get("purpose") != "bounded_live_source_probe":
        return False
    findings = report.get("findings", {})
    protected_false = (
        "majles_live_route_confirmed", "pilot_document_93849_downloaded",
        "project_runtime_connectivity_proven", "local_pdf_downloaded", "ocr_run",
        "staging_written", "active_bank_modified", "legal_validity_assessed",
    )
    if any(findings.get(k) is not False for k in protected_false):
        return False
    if findings.get("ekhtebar_is_secondary_only") is not True:
        return False
    for item in report.get("evidence", []):
        parsed = urlparse(item.get("url", ""))
        if parsed.scheme != "https" or parsed.hostname not in {"rc.majlis.ir", "www.ekhtebar.ir"}:
            return False
    digest = report.get("report_sha256")
    unhashed = dict(report)
    unhashed.pop("report_sha256", None)
    canonical = json.dumps(unhashed, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return digest == sha256(canonical).hexdigest()
