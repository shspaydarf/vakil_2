"""Stage 1 quality: editable DOCX and searchable PDF exports."""
from io import BytesIO
import zipfile

import fitz
import pytest

from legal_bot.output_engine import build_case_docx, build_case_pdf

SAMPLE = {
    "status": "PASS",
    "draft_text": (
        "ریاست محترم دادگاه\n\n"
        "با سلام و احترام\n"
        "اینجانب نسبت به موضوع پرونده اعتراض دارم.\n"
        "خواسته: رسیدگی قانونی\n"
        "تاریخ: ۱۴۰۵/۰۷/۰۷"
    ),
}


def test_docx_export_is_valid_editable_word_document():
    payload = build_case_docx(SAMPLE)
    assert payload.startswith(b"PK")
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        assert "word/document.xml" in archive.namelist()
        xml = archive.read("word/document.xml").decode("utf-8")
        assert "ریاست محترم دادگاه" in xml
        assert "w:bidi" in xml
        assert "پیش‌نویس لایحه دفاعیه" in xml


def test_pdf_export_contains_selectable_searchable_text():
    payload = build_case_pdf(SAMPLE)
    assert payload.startswith(b"%PDF")
    with fitz.open(stream=payload, filetype="pdf") as pdf:
        extracted = "\n".join(page.get_text() for page in pdf)
        assert len(extracted.strip()) > 50
        assert "ریاست" in extracted
        assert "دادگاه" in extracted


def test_empty_draft_is_rejected_for_both_formats():
    with pytest.raises(ValueError):
        build_case_docx({"draft_text": ""})
    with pytest.raises(ValueError):
        build_case_pdf({"draft_text": ""})
