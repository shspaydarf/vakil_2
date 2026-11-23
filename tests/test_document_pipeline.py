import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import fitz

from legal_bot.ingestion.document_pipeline import process_pdf_document, DocumentPipelineError


class DocumentPipelineTests(unittest.TestCase):
    def _pdf(self, path: Path, text: str | None = None):
        doc = fitz.open()
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
        doc.save(path)
        doc.close()

    def test_text_pdf_runs_pipeline_without_ocr(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "law.pdf"
            self._pdf(source, "قانون آزمایشی\nماده ۱ - متن ماده قانونی برای آزمون")
            before = hashlib.sha256(source.read_bytes()).hexdigest()
            result = process_pdf_document(source, root / "out")
            self.assertEqual(result.page_count, 1)
            self.assertEqual(result.ocr_page_numbers, [])
            self.assertEqual(result.stage_status["persian_ocr"], "not_required")
            self.assertTrue((root / "out" / "05_staging_document.json").is_file())
            self.assertTrue((root / "out" / "manifest.json").is_file())
            self.assertEqual(before, hashlib.sha256(source.read_bytes()).hexdigest())
            payload = json.loads((root / "out" / "05_staging_document.json").read_text())
            self.assertFalse(payload["imported_to_active_legal_bank"])
            self.assertEqual(payload["pages"][0]["provenance"], "pdf_text_extraction")

    def test_sparse_page_ocr_is_merged_with_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "scan.pdf"
            self._pdf(source)
            fake_ocr = SimpleNamespace(
                pages=[{"page_number": 1, "text": "قانون آزمایشی ماده ۱ متن OCR شده", "status": "ocr_completed", "mean_confidence": 88.0, "warnings": []}],
                ocr_pages=[1], review_required=True,
                to_dict=lambda: {"pages": [{"page_number": 1, "text": "قانون آزمایشی ماده ۱ متن OCR شده", "status": "ocr_completed", "mean_confidence": 88.0, "warnings": []}], "ocr_pages": [1], "review_required": True},
            )
            with patch("legal_bot.ingestion.document_pipeline.ocr_pdf_pages", return_value=fake_ocr):
                with patch("legal_bot.ingestion.document_pipeline.write_ocr_json", side_effect=lambda r, p: Path(p).write_text(json.dumps(r.to_dict()))):
                    result = process_pdf_document(source, root / "out")
            self.assertEqual(result.ocr_page_numbers, [1])
            payload = json.loads((root / "out" / "05_staging_document.json").read_text())
            page = payload["pages"][0]
            self.assertEqual(page["provenance"], "tesseract_ocr_machine_generated")
            self.assertEqual(page["extraction_text"], "")
            self.assertIn("متن OCR شده", page["text"])
            self.assertTrue(payload["review_required"])

    def test_empty_ocr_does_not_overwrite_extracted_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "law.pdf"
            self._pdf(source, "A sufficiently long text block for the extraction test")
            # Force the extraction classifier to mark the page sparse while preserving its text.
            from legal_bot.ingestion.pdf_text_extractor import ExtractionPolicy
            fake_ocr = SimpleNamespace(
                pages=[{"page_number": 1, "text": "", "status": "empty_result", "warnings": ["empty"]}],
                ocr_pages=[1], review_required=True,
                to_dict=lambda: {"pages": [{"page_number": 1, "text": "", "status": "empty_result", "warnings": ["empty"]}], "ocr_pages": [1], "review_required": True},
            )
            with patch("legal_bot.ingestion.document_pipeline.ocr_pdf_pages", return_value=fake_ocr):
                with patch("legal_bot.ingestion.document_pipeline.write_ocr_json", side_effect=lambda r, p: Path(p).write_text(json.dumps(r.to_dict()))):
                    result = process_pdf_document(source, root / "out", extraction_policy=ExtractionPolicy(min_chars_per_page=500))
            payload = json.loads((root / "out" / "05_staging_document.json").read_text())
            self.assertIn("sufficiently long", payload["pages"][0]["text"])
            self.assertEqual(payload["pages"][0]["provenance"], "pdf_text_extraction")

    def test_missing_pdf_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(DocumentPipelineError):
                process_pdf_document(Path(tmp) / "missing.pdf", Path(tmp) / "out")


if __name__ == "__main__":
    unittest.main()
