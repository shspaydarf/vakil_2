import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fitz

from legal_bot.ingestion.persian_pdf_ocr import (
    OCRPolicy, PDFOCRError, ocr_pdf_pages, write_ocr_json,
)


def make_pdf(path: Path, pages=1):
    doc = fitz.open()
    for _ in range(pages):
        doc.new_page()
    doc.save(path)
    doc.close()


class PersianPDFOCRTests(unittest.TestCase):
    def fake_data(self, *_args, **_kwargs):
        return {"text": ["ماده", "اول", "قانون"], "conf": ["91", "88", "90"]}

    def test_auto_selects_sparse_pages_and_marks_machine_output(self):
        with tempfile.TemporaryDirectory() as td:
            pdf = Path(td) / "scan.pdf"
            make_pdf(pdf, 2)
            original = pdf.read_bytes()
            with patch("pytesseract.image_to_data", side_effect=self.fake_data):
                result = ocr_pdf_pages(pdf)
            self.assertEqual(result.ocr_pages, [1, 2])
            self.assertEqual(result.pages[0]["status"], "ocr_completed")
            self.assertTrue(result.review_required)
            self.assertEqual(pdf.read_bytes(), original)

    def test_explicit_page_selection_and_sidecar(self):
        with tempfile.TemporaryDirectory() as td:
            pdf = Path(td) / "scan.pdf"
            make_pdf(pdf, 2)
            with patch("pytesseract.image_to_data", side_effect=self.fake_data):
                result = ocr_pdf_pages(pdf, page_numbers=[2])
            out = write_ocr_json(result, Path(td) / "ocr" / "result.json")
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(payload["ocr_pages"], [2])
            self.assertEqual(payload["provenance"], "tesseract_ocr_machine_generated")

    def test_invalid_page_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            pdf = Path(td) / "scan.pdf"
            make_pdf(pdf, 1)
            with self.assertRaises(PDFOCRError):
                ocr_pdf_pages(pdf, page_numbers=[0])

    def test_hash_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            pdf = Path(td) / "scan.pdf"
            make_pdf(pdf)
            with self.assertRaises(PDFOCRError):
                ocr_pdf_pages(pdf, page_numbers=[1], expected_sha256="f" * 64)

    def test_missing_language_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            pdf = Path(td) / "scan.pdf"
            make_pdf(pdf)
            with self.assertRaises(PDFOCRError):
                ocr_pdf_pages(pdf, page_numbers=[1], policy=OCRPolicy(languages="machina_missing"))

    def test_low_confidence_is_flagged_for_review(self):
        with tempfile.TemporaryDirectory() as td:
            pdf = Path(td) / "scan.pdf"
            make_pdf(pdf)
            low = {"text": ["قانون"], "conf": ["4"]}
            with patch("pytesseract.image_to_data", return_value=low):
                result = ocr_pdf_pages(pdf, page_numbers=[1])
            self.assertEqual(result.pages[0]["status"], "low_confidence")
            self.assertTrue(result.pages[0]["warnings"])


if __name__ == "__main__":
    unittest.main()
