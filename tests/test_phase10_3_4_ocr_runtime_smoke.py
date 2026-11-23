"""Runtime smoke tests using a locally generated scanned-PDF fixture.

This validates installed PyMuPDF/Tesseract integration, not a live official-source
PDF. Network acquisition is deliberately excluded from this test.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import fitz
from PIL import Image, ImageDraw, ImageFont
import pytest

from legal_bot.ingestion.pdf_text_extractor import extract_pdf_text
from legal_bot.ingestion.persian_pdf_ocr import OCRPolicy, PDFOCRError, ocr_pdf_pages, write_ocr_json


def _make_scanned_pdf(path: Path) -> None:
    image = Image.new("RGB", (1600, 900), "white")
    draw = ImageDraw.Draw(image)
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    font = ImageFont.truetype(font_path, 88)
    draw.text((120, 300), "LEGAL DOCUMENT 2026", fill="black", font=font)
    draw.text((120, 430), "OFFICIAL RECORD 1709520", fill="black", font=font)
    pix = image.tobytes()
    # Embed the raster as a single-page PDF; there is intentionally no PDF text layer.
    doc = fitz.open()
    page = doc.new_page(width=800, height=450)
    page.insert_image(page.rect, stream=_png_bytes(image))
    doc.save(path)
    doc.close()


def _png_bytes(image: Image.Image) -> bytes:
    import io
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def test_runtime_extractor_flags_scanned_fixture_for_ocr(tmp_path):
    pdf = tmp_path / "scanned.pdf"
    _make_scanned_pdf(pdf)
    result = extract_pdf_text(pdf)
    assert result.page_count == 1
    assert result.needs_ocr is True
    assert result.scan_or_ocr_page_numbers == [1]


def test_runtime_tesseract_ocr_processes_scanned_fixture(tmp_path):
    pdf = tmp_path / "scanned.pdf"
    _make_scanned_pdf(pdf)
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    result = ocr_pdf_pages(pdf, page_numbers=[1], expected_sha256=digest,
                           policy=OCRPolicy(languages="fas+eng", dpi=180, min_confidence=10))
    assert result.page_count == 1
    assert result.ocr_pages == [1]
    assert result.provenance == "tesseract_ocr_machine_generated"
    assert "LEGAL" in result.pages[0]["text"].upper()
    assert result.review_required is True


def test_runtime_ocr_rejects_manifest_hash_mismatch(tmp_path):
    pdf = tmp_path / "scanned.pdf"
    _make_scanned_pdf(pdf)
    with pytest.raises(PDFOCRError, match="هش PDF"):
        ocr_pdf_pages(pdf, page_numbers=[1], expected_sha256="0" * 64,
                      policy=OCRPolicy(languages="fas+eng", dpi=180))


def test_runtime_ocr_sidecar_is_separate_and_traceable(tmp_path):
    pdf = tmp_path / "scanned.pdf"
    _make_scanned_pdf(pdf)
    result = ocr_pdf_pages(pdf, page_numbers=[1],
                           policy=OCRPolicy(languages="fas+eng", dpi=180, min_confidence=10))
    sidecar = write_ocr_json(result, tmp_path / "output" / "ocr.json")
    assert sidecar.is_file()
    assert pdf.is_file()
    import json
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert payload["source_sha256"] == hashlib.sha256(pdf.read_bytes()).hexdigest()
    assert payload["review_required"] is True
