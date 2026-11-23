# -*- coding: utf-8 -*-
"""Deterministic, page-preserving text extraction for staged legal PDFs.

This module never modifies the source PDF and never writes to the active law bank.
Scanned/low-text pages are flagged for the separate OCR stage (3.4).
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class PDFTextExtractionError(ValueError):
    """The input PDF could not be safely or consistently extracted."""


@dataclass(frozen=True)
class ExtractionPolicy:
    min_chars_per_page: int = 40
    min_text_page_ratio: float = 0.60
    max_pages: int = 2000
    sort_blocks_reading_order: bool = True


@dataclass(frozen=True)
class PDFTextExtraction:
    source_path: str
    source_sha256: str
    page_count: int
    extracted_at: str
    document_text_chars: int
    text_page_count: int
    scan_or_ocr_page_numbers: list[int]
    needs_ocr: bool
    pages: list[dict[str, Any]]
    quality: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_pdf_text(pdf_path: str | Path, *, policy: ExtractionPolicy | None = None,
                     expected_sha256: str | None = None) -> PDFTextExtraction:
    """Extract page text and geometry; page numbers are 1-based in the output."""
    try:
        import fitz
    except ImportError as exc:  # pragma: no cover - dependency is part of the project
        raise PDFTextExtractionError("کتابخانه PyMuPDF نصب نیست") from exc

    source = Path(pdf_path)
    if not source.is_file():
        raise PDFTextExtractionError("فایل PDF ورودی پیدا نشد")
    policy = policy or ExtractionPolicy()
    digest = _sha256_file(source)
    if expected_sha256 and digest.lower() != expected_sha256.lower():
        raise PDFTextExtractionError("هش فایل با manifest دریافت مطابقت ندارد")

    try:
        document = fitz.open(str(source))
    except Exception as exc:
        raise PDFTextExtractionError("بازکردن PDF برای استخراج متن ناموفق بود") from exc

    pages: list[dict[str, Any]] = []
    scan_pages: list[int] = []
    text_pages = 0
    total_chars = 0
    try:
        if document.is_encrypted:
            raise PDFTextExtractionError("PDF رمزگذاری‌شده قابل استخراج نیست")
        if document.page_count < 1 or document.page_count > policy.max_pages:
            raise PDFTextExtractionError("تعداد صفحات PDF خارج از محدوده مجاز است")

        for index, page in enumerate(document):
            page_no = index + 1
            try:
                raw = page.get_text("dict", sort=policy.sort_blocks_reading_order)
                text_blocks: list[dict[str, Any]] = []
                for block in raw.get("blocks", []):
                    if block.get("type") != 0:
                        continue
                    lines: list[str] = []
                    for line in block.get("lines", []):
                        spans = line.get("spans", [])
                        line_text = "".join(span.get("text", "") for span in spans)
                        if line_text:
                            lines.append(line_text)
                    block_text = "\n".join(lines).strip()
                    if block_text:
                        bbox = [round(float(v), 2) for v in block.get("bbox", (0, 0, 0, 0))]
                        text_blocks.append({"bbox": bbox, "text": block_text})
                # Stable geometric order, independent of PDF internal object order.
                if policy.sort_blocks_reading_order:
                    text_blocks.sort(key=lambda b: (round(b["bbox"][1], 1), b["bbox"][0]))
                page_text = "\n".join(item["text"] for item in text_blocks).strip()
                char_count = len(page_text)
                total_chars += char_count
                if char_count >= policy.min_chars_per_page:
                    text_pages += 1
                else:
                    scan_pages.append(page_no)
                image_count = sum(1 for b in raw.get("blocks", []) if b.get("type") == 1)
                pages.append({
                    "page_number": page_no,
                    "text": page_text,
                    "blocks": text_blocks,
                    "character_count": char_count,
                    "image_block_count": image_count,
                    "likely_scanned_or_text_sparse": char_count < policy.min_chars_per_page,
                })
            except Exception as exc:
                raise PDFTextExtractionError(f"استخراج صفحه {page_no} ناموفق بود") from exc
    finally:
        document.close()

    ratio = text_pages / len(pages) if pages else 0.0
    needs_ocr = bool(scan_pages) or ratio < policy.min_text_page_ratio
    quality = {
        "text_page_ratio": round(ratio, 4),
        "minimum_chars_per_page": policy.min_chars_per_page,
        "minimum_text_page_ratio": policy.min_text_page_ratio,
        "classification": "needs_ocr" if needs_ocr else "text_extractable",
        "note": "این سنجه غربالگری است؛ کیفیت حقوقی و کامل‌بودن متن باید در مرحله اعتبارسنجی بررسی شود.",
    }
    return PDFTextExtraction(
        source_path=str(source.resolve()), source_sha256=digest,
        page_count=len(pages), extracted_at=datetime.now(timezone.utc).isoformat(),
        document_text_chars=total_chars, text_page_count=text_pages,
        scan_or_ocr_page_numbers=scan_pages, needs_ocr=needs_ocr,
        pages=pages, quality=quality,
    )


def write_extraction_json(result: PDFTextExtraction, output_path: str | Path) -> Path:
    """Atomically persist extraction output as a separate sidecar JSON."""
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(result.to_dict(), stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, target)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return target
