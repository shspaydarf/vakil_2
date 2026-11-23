# -*- coding: utf-8 -*-
"""Bounded batch extraction/OCR orchestration for acquired legal PDFs.

This layer consumes an explicit manifest; it never discovers files recursively,
fetches URLs, mutates source PDFs, or writes to the active legal bank.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .document_pipeline import process_pdf_document


class BulkProcessingError(ValueError):
    """The batch manifest or policy is invalid."""


@dataclass(frozen=True)
class BulkProcessingPolicy:
    max_documents: int = 50
    max_total_bytes: int = 512 * 1024 * 1024
    max_pages_per_document: int = 2000
    max_total_pages: int = 10000
    max_documents_per_source: int = 25
    allow_secondary_sources: bool = False
    run_ocr: bool = False


@dataclass(frozen=True)
class BulkPDFItem:
    document_id: str
    source_id: str
    source_class: str
    source_verified: bool
    acquisition_status: str
    pdf_path: str
    expected_sha256: str | None = None
    document_type: str = "unknown"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def _validate_item(item: BulkPDFItem, policy: BulkProcessingPolicy) -> Path:
    if not item.document_id.strip() or not item.source_id.strip():
        raise BulkProcessingError("شناسه سند و منبع الزامی است")
    if item.acquisition_status != "downloaded":
        raise BulkProcessingError("سند در وضعیت downloaded نیست")
    if item.source_class not in ({"official_primary", "secondary"} if policy.allow_secondary_sources else {"official_primary"}):
        raise BulkProcessingError("کلاس منبع برای پردازش دسته‌ای مجاز نیست")
    if not item.source_verified:
        raise BulkProcessingError("منبع هنوز تأیید انسانی نشده است")
    path = Path(item.pdf_path)
    if not path.is_file() or path.suffix.lower() != ".pdf":
        raise BulkProcessingError("مسیر ورودی باید به فایل PDF موجود اشاره کند")
    if path.stat().st_size <= 0 or path.stat().st_size > policy.max_total_bytes:
        raise BulkProcessingError("اندازه فایل خارج از محدوده مجاز است")
    if item.expected_sha256 and _sha256(path).lower() != item.expected_sha256.lower():
        raise BulkProcessingError("هش فایل با manifest دریافت مطابقت ندارد")
    return path


def process_bulk_pdfs(
    items: Iterable[BulkPDFItem], output_root: str | Path, *,
    policy: BulkProcessingPolicy | None = None,
) -> dict[str, Any]:
    """Process a bounded explicit batch; isolate item failures and emit a report.

    OCR is opt-in. A failed document does not stop other documents. Budget
    overflow is rejected before processing, not silently truncated.
    """
    policy = policy or BulkProcessingPolicy()
    if min(policy.max_documents, policy.max_total_bytes, policy.max_pages_per_document,
           policy.max_total_pages, policy.max_documents_per_source) < 1:
        raise BulkProcessingError("محدودیت‌های پردازش باید مثبت باشند")
    batch = list(items)
    if not batch:
        raise BulkProcessingError("فهرست اسناد خالی است")
    if len(batch) > policy.max_documents:
        raise BulkProcessingError("تعداد اسناد از سقف دسته بیشتر است")
    ids = [x.document_id for x in batch]
    if len(ids) != len(set(ids)):
        raise BulkProcessingError("شناسه سند تکراری در manifest وجود دارد")

    validated: list[tuple[BulkPDFItem, Path]] = []
    total_bytes = 0
    source_counts: dict[str, int] = {}
    for item in batch:
        path = _validate_item(item, policy)
        total_bytes += path.stat().st_size
        source_counts[item.source_id] = source_counts.get(item.source_id, 0) + 1
        if source_counts[item.source_id] > policy.max_documents_per_source:
            raise BulkProcessingError("سقف تعداد اسناد برای یک منبع رد شده است")
        validated.append((item, path))
    if total_bytes > policy.max_total_bytes:
        raise BulkProcessingError("حجم کل دسته از سقف مجاز بیشتر است")

    root = Path(output_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    page_total = 0
    for item, path in validated:
        safe_id = re.sub(r"[^A-Za-z0-9._-]+", "_", item.document_id).strip("._")[:80] or hashlib.sha256(item.document_id.encode()).hexdigest()[:16]
        out_dir = root / safe_id
        try:
            # Preflight page count before invoking OCR/normalization pipeline.
            import fitz
            with fitz.open(str(path)) as pdf:
                page_count = pdf.page_count
                encrypted = pdf.is_encrypted
            if encrypted or page_count < 1 or page_count > policy.max_pages_per_document:
                raise BulkProcessingError("PDF رمزگذاری‌شده یا دارای تعداد صفحات خارج از محدوده است")
            if page_total + page_count > policy.max_total_pages:
                raise BulkProcessingError("سقف مجموع صفحات دسته رد شده است")
            page_total += page_count
            result = process_pdf_document(
                path, out_dir, document_type=item.document_type, run_ocr=policy.run_ocr,
            )
            results.append({
                "document_id": item.document_id, "source_id": item.source_id,
                "status": "completed_review_required", "source_sha256": result.source_sha256,
                "page_count": result.page_count, "ocr_page_numbers": result.ocr_page_numbers,
                "output_dir": str(out_dir), "manifest": str(out_dir / "manifest.json"),
                "active_bank_imported": False,
            })
        except Exception as exc:
            results.append({
                "document_id": item.document_id, "source_id": item.source_id,
                "status": "failed", "error_type": type(exc).__name__,
                "error": str(exc)[:500], "active_bank_imported": False,
            })
    report = {
        "schema_version": "1.0", "processor": "bulk_document_processing",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "policy": asdict(policy), "submitted_documents": len(batch),
        "completed_documents": sum(r["status"] == "completed_review_required" for r in results),
        "failed_documents": sum(r["status"] == "failed" for r in results),
        "processed_page_count": page_total, "results": results,
        "review_required": True, "active_bank_modified": False,
        "warnings": [
            "متن استخراجی و OCR ماشین‌ساخته است و اصالت یا اعتبار حقوقی سند را اثبات نمی‌کند.",
            "ورود به بانک فعال در این مرحله انجام نمی‌شود.",
        ],
    }
    _atomic_json(root / "bulk_processing_report.json", report)
    return report
