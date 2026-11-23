# -*- coding: utf-8 -*-
"""Bounded Persian OCR for scanned pages in staged legal PDFs.

OCR is opt-in, page-scoped, and writes a separate sidecar. The source PDF and
active legal JSON bank are never modified. OCR text is explicitly marked as
machine-generated and must be reviewed before legal use.
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


class PDFOCRError(ValueError):
    """OCR could not be performed within the configured safety limits."""


@dataclass(frozen=True)
class OCRPolicy:
    languages: str = "fas+eng"
    dpi: int = 220
    max_dpi: int = 300
    max_pixels_per_page: int = 25_000_000
    max_pages: int = 2000
    max_page_seconds: int = 90
    min_confidence: float = 25.0
    tesseract_config: str = "--oem 1 --psm 3"


@dataclass(frozen=True)
class PageOCR:
    page_number: int
    text: str
    mean_confidence: float | None
    word_count: int
    language: str
    status: str
    warnings: list[str]


@dataclass(frozen=True)
class PDFOCRResult:
    source_path: str
    source_sha256: str
    page_count: int
    ocr_pages: list[int]
    languages: str
    dpi: int
    processed_at: str
    pages: list[dict[str, Any]]
    review_required: bool
    provenance: str = "tesseract_ocr_machine_generated"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_languages(pytesseract: Any, languages: str) -> None:
    requested = [part.strip() for part in languages.split("+") if part.strip()]
    if not requested or any(not part.replace("_", "").isalnum() for part in requested):
        raise PDFOCRError("شناسه زبان OCR نامعتبر است")
    try:
        available = set(pytesseract.get_languages(config=""))
    except Exception as exc:
        raise PDFOCRError("امکان بررسی زبان‌های نصب‌شده Tesseract وجود ندارد") from exc
    missing = sorted(set(requested) - available)
    if missing:
        raise PDFOCRError("زبان OCR نصب نیست: " + ", ".join(missing))


def ocr_pdf_pages(pdf_path: str | Path, *, page_numbers: list[int] | None = None,
                  policy: OCRPolicy | None = None,
                  expected_sha256: str | None = None) -> PDFOCRResult:
    """OCR selected 1-based pages; defaults to pages flagged by text extraction.

    Page selection is based on the existing extractor's sparse-page classifier.
    Explicit page_numbers override that selection. No automatic OCR is run on
    pages already containing sufficient text.
    """
    source = Path(pdf_path)
    if not source.is_file():
        raise PDFOCRError("فایل PDF ورودی پیدا نشد")
    policy = policy or OCRPolicy()
    dpi = max(72, min(int(policy.dpi), int(policy.max_dpi), 300))
    try:
        import fitz
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        raise PDFOCRError("برای OCR به PyMuPDF، pytesseract و Pillow نیاز است") from exc

    digest = _file_hash(source)
    if expected_sha256 and digest.lower() != expected_sha256.lower():
        raise PDFOCRError("هش PDF با manifest ورودی مطابقت ندارد")
    try:
        document = fitz.open(str(source))
    except Exception as exc:
        raise PDFOCRError("بازکردن PDF برای OCR ناموفق بود") from exc

    try:
        if document.is_encrypted:
            raise PDFOCRError("PDF رمزگذاری‌شده قابل OCR نیست")
        page_count = document.page_count
        if page_count < 1 or page_count > policy.max_pages:
            raise PDFOCRError("تعداد صفحات PDF خارج از محدوده مجاز است")
        if page_numbers is None:
            from .pdf_text_extractor import extract_pdf_text
            extracted = extract_pdf_text(source, expected_sha256=digest)
            selected = list(extracted.scan_or_ocr_page_numbers)
        else:
            selected = sorted(set(int(n) for n in page_numbers))
        if not selected:
            raise PDFOCRError("صفحه‌ای برای OCR انتخاب نشده است")
        if any(n < 1 or n > page_count for n in selected):
            raise PDFOCRError("شماره صفحه انتخاب‌شده خارج از محدوده PDF است")
        _validate_languages(pytesseract, policy.languages)

        results: list[dict[str, Any]] = []
        for page_no in selected:
            warnings: list[str] = []
            try:
                page = document.load_page(page_no - 1)
                scale = dpi / 72.0
                estimated_pixels = int(page.rect.width * scale) * int(page.rect.height * scale)
                if estimated_pixels > policy.max_pixels_per_page:
                    scale *= (policy.max_pixels_per_page / estimated_pixels) ** 0.5
                    warnings.append("وضوح تصویر برای رعایت سقف حافظه کاهش یافت")
                matrix = fitz.Matrix(scale, scale)
                pix = page.get_pixmap(matrix=matrix, colorspace=fitz.csRGB, alpha=False)
                if pix.width * pix.height > policy.max_pixels_per_page:
                    raise PDFOCRError("ابعاد تصویر صفحه از سقف مجاز بیشتر است")
                image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                data = pytesseract.image_to_data(
                    image, lang=policy.languages, config=policy.tesseract_config,
                    output_type=pytesseract.Output.DICT,
                    timeout=max(1, int(policy.max_page_seconds)),
                )
                words: list[str] = []
                confidences: list[float] = []
                for token, raw_conf in zip(data.get("text", []), data.get("conf", [])):
                    token = str(token).strip()
                    try:
                        confidence = float(raw_conf)
                    except (TypeError, ValueError):
                        confidence = -1.0
                    if token and confidence >= 0:
                        words.append(token)
                        confidences.append(confidence)
                text = " ".join(words).strip()
                mean_conf = round(sum(confidences) / len(confidences), 2) if confidences else None
                status = "ocr_completed"
                if not text:
                    status = "empty_result"
                    warnings.append("متنی از صفحه شناسایی نشد")
                elif mean_conf is None or mean_conf < policy.min_confidence:
                    status = "low_confidence"
                    warnings.append("اعتماد OCR پایین است؛ بازبینی انسانی ضروری است")
                results.append(asdict(PageOCR(
                    page_number=page_no, text=text, mean_confidence=mean_conf,
                    word_count=len(words), language=policy.languages,
                    status=status, warnings=warnings,
                )))
            except PDFOCRError:
                raise
            except Exception as exc:
                raise PDFOCRError(f"OCR صفحه {page_no} ناموفق بود: {type(exc).__name__}") from exc
        return PDFOCRResult(
            source_path=str(source.resolve()), source_sha256=digest,
            page_count=page_count, ocr_pages=selected, languages=policy.languages,
            dpi=dpi, processed_at=datetime.now(timezone.utc).isoformat(),
            pages=results, review_required=True,
        )
    finally:
        document.close()


def write_ocr_json(result: PDFOCRResult, output_path: str | Path) -> Path:
    """Atomically save OCR output as a separate JSON sidecar."""
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
