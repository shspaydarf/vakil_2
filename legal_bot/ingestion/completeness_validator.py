# -*- coding: utf-8 -*-
"""Conservative completeness screening for staged Iranian legal documents.

This module detects structural/page anomalies. It cannot prove that a source
PDF itself is complete, and it never modifies the source or active law bank.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

def _number(value: Any) -> int | None:
    raw = str(value or "").translate(_DIGITS).strip()
    return int(raw) if raw.isdigit() else None

def _page_number(page: dict[str, Any]) -> int | None:
    return _number(page.get("page_number"))

@dataclass(frozen=True)
class CompletenessReport:
    checked_at: str
    validator_version: str
    status: str
    checks: dict[str, str]
    findings: list[dict[str, Any]]
    metrics: dict[str, Any]
    source_sha256: str | None
    review_required: bool = True
    completeness_proven: bool = False
    active_bank_imported: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_document_completeness(
    pages: list[dict[str, Any]], structure: dict[str, Any] | None = None,
    *, expected_page_count: int | None = None, source_sha256: str | None = None,
) -> CompletenessReport:
    """Screen page continuity, empty pages, article numbering and nested units.

    Findings are deliberately phrased as possible omissions: numbering gaps
    may be intentional (e.g. repealed articles), and blank pages may be valid.
    """
    if not isinstance(pages, list) or not pages:
        raise ValueError("فهرست صفحات برای بررسی کامل‌بودن خالی است")
    structure = structure or {}
    findings: list[dict[str, Any]] = []
    checks: dict[str, str] = {}

    nums = [_page_number(p) for p in pages]
    valid_nums = [n for n in nums if n is not None]
    duplicate_pages = sorted({n for n in valid_nums if valid_nums.count(n) > 1})
    missing_page_numbers = sorted(set(range(1, max(valid_nums, default=0) + 1)) - set(valid_nums))
    if any(n is None for n in nums) or duplicate_pages or missing_page_numbers:
        checks["page_sequence"] = "anomaly"
        findings.append({"code": "page_sequence_anomaly", "severity": "high",
                         "details": {"invalid_page_entries": nums.count(None), "duplicate_page_numbers": duplicate_pages,
                                     "missing_page_numbers": missing_page_numbers}})
    else:
        checks["page_sequence"] = "sequential"

    observed_count = len(pages)
    if expected_page_count is not None and expected_page_count != observed_count:
        checks["page_count_match"] = "mismatch"
        findings.append({"code": "page_count_mismatch", "severity": "high",
                         "details": {"expected": expected_page_count, "observed": observed_count}})
    else:
        checks["page_count_match"] = "matches_or_not_supplied"

    empty_pages = []
    low_confidence_pages = []
    for page in pages:
        pn = _page_number(page)
        if not str(page.get("text", "")).strip():
            empty_pages.append(pn)
        confidence = page.get("ocr_mean_confidence")
        try:
            if confidence is not None and float(confidence) < 45:
                low_confidence_pages.append(pn)
        except (TypeError, ValueError):
            pass
    if empty_pages:
        checks["page_text_presence"] = "empty_pages_found"
        findings.append({"code": "empty_text_pages", "severity": "high",
                         "details": {"page_numbers": empty_pages, "note": "ممکن است صفحه عمداً سفید یا دارای محتوای تصویری باشد."}})
    else:
        checks["page_text_presence"] = "all_pages_have_text"
    if low_confidence_pages:
        checks["ocr_confidence"] = "low_confidence_pages_found"
        findings.append({"code": "low_ocr_confidence", "severity": "medium",
                         "details": {"page_numbers": low_confidence_pages}})
    else:
        checks["ocr_confidence"] = "no_low_confidence_scores_reported"

    articles = structure.get("articles", []) if isinstance(structure, dict) else []
    article_numbers = [_number(a.get("number")) for a in articles if isinstance(a, dict)]
    article_numbers = [n for n in article_numbers if n is not None]
    duplicates = sorted({n for n in article_numbers if article_numbers.count(n) > 1})
    if duplicates:
        checks["article_number_uniqueness"] = "duplicates_found"
        findings.append({"code": "duplicate_article_numbers", "severity": "high", "details": {"numbers": duplicates}})
    else:
        checks["article_number_uniqueness"] = "no_numeric_duplicates"

    gaps: list[int] = []
    ordered = sorted(set(article_numbers))
    for left, right in zip(ordered, ordered[1:]):
        if right - left > 1:
            gaps.extend(range(left + 1, right))
    if gaps:
        checks["article_number_continuity"] = "possible_gaps"
        findings.append({"code": "possible_missing_articles", "severity": "medium",
                         "details": {"missing_numbers": gaps,
                                     "note": "شماره‌های حذف‌شده یا نسخ‌شده ممکن است عمدی باشند؛ با منبع رسمی تطبیق شود."}})
    else:
        checks["article_number_continuity"] = "no_numeric_gaps_detected"

    duplicate_notes: list[dict[str, Any]] = []
    for article in articles:
        if not isinstance(article, dict):
            continue
        note_nums = [_number(note.get("number")) for note in article.get("notes", []) if isinstance(note, dict)]
        note_nums = [n for n in note_nums if n is not None]
        repeated = sorted({n for n in note_nums if note_nums.count(n) > 1})
        if repeated:
            duplicate_notes.append({"article": article.get("number"), "numbers": repeated})
    if duplicate_notes:
        checks["note_number_uniqueness"] = "duplicates_found"
        findings.append({"code": "duplicate_note_numbers", "severity": "medium", "details": {"items": duplicate_notes}})
    else:
        checks["note_number_uniqueness"] = "no_numeric_duplicates"

    invalid_refs: list[dict[str, Any]] = []
    max_page = max(valid_nums, default=0)
    for article in articles:
        if not isinstance(article, dict):
            continue
        for key in ("start_page", "end_page"):
            ref = _number(article.get(key))
            if ref is not None and (ref < 1 or ref > max_page):
                invalid_refs.append({"article": article.get("number"), "field": key, "page": ref})
    if invalid_refs:
        checks["structure_page_references"] = "out_of_range"
        findings.append({"code": "structure_page_reference_out_of_range", "severity": "high", "details": {"references": invalid_refs}})
    else:
        checks["structure_page_references"] = "within_observed_range"

    high = any(f["severity"] == "high" for f in findings)
    medium = any(f["severity"] == "medium" for f in findings)
    status = "critical_anomalies_found" if high else "review_recommended" if medium else "screening_no_anomaly_detected"
    return CompletenessReport(
        checked_at=datetime.now(timezone.utc).isoformat(), validator_version="4.3.0",
        status=status, checks=checks, findings=findings,
        metrics={"observed_page_count": observed_count, "recognized_article_count": len(articles),
                 "numeric_article_count": len(article_numbers), "empty_page_count": len(empty_pages),
                 "low_ocr_confidence_page_count": len(low_confidence_pages)},
        source_sha256=source_sha256, review_required=True,
    )


def write_completeness_report(report: CompletenessReport, output_path: str | Path) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(report.to_dict(), stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, target)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return target


def validate_staging_document(staging_document: dict[str, Any]) -> CompletenessReport:
    """Validate a Phase 3.7 ``05_staging_document.json`` payload directly."""
    if not isinstance(staging_document, dict):
        raise ValueError("بسته سند مرحله آماده‌سازی معتبر نیست")
    source = staging_document.get("source") or {}
    if not isinstance(source, dict):
        source = {}
    page_count = _number(source.get("page_count"))
    return validate_document_completeness(
        staging_document.get("pages") or [],
        staging_document.get("structure") or {},
        expected_page_count=page_count,
        source_sha256=source.get("sha256"),
    )
