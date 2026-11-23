import json
import tempfile
import unittest
from pathlib import Path

import fitz

from legal_bot.ingestion.pdf_text_extractor import (
    ExtractionPolicy, PDFTextExtractionError, extract_pdf_text, write_extraction_json,
)


def make_pdf(path: Path, texts):
    doc = fitz.open()
    for value in texts:
        page = doc.new_page()
        if value:
            page.insert_text((72, 72), value, fontsize=11)
    doc.save(path)
    doc.close()


class PDFTextExtractorTests(unittest.TestCase):
    def test_extracts_text_page_and_preserves_source(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "law.pdf"
            make_pdf(source, ["ماده ۱ ـ MACHINA legal text " * 5, "تبصره ـ second page " * 5])
            original = source.read_bytes()
            result = extract_pdf_text(source)
            self.assertEqual(result.page_count, 2)
            self.assertIn("MACHINA", result.pages[0]["text"])
            self.assertFalse(result.needs_ocr)
            self.assertEqual(source.read_bytes(), original)

    def test_flags_scanned_or_empty_pages_for_ocr(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "scan.pdf"
            make_pdf(source, [""])
            result = extract_pdf_text(source)
            self.assertTrue(result.needs_ocr)
            self.assertEqual(result.scan_or_ocr_page_numbers, [1])

    def test_mixed_document_flags_only_sparse_page(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "mixed.pdf"
            make_pdf(source, ["متن حقوقی " * 20, ""])
            result = extract_pdf_text(source)
            self.assertEqual(result.scan_or_ocr_page_numbers, [2])
            self.assertTrue(result.needs_ocr)

    def test_expected_hash_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "law.pdf"
            make_pdf(source, ["text " * 20])
            with self.assertRaises(PDFTextExtractionError):
                extract_pdf_text(source, expected_sha256="0" * 64)

    def test_page_limit_enforced(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "law.pdf"
            make_pdf(source, ["text " * 20, "text " * 20])
            with self.assertRaises(PDFTextExtractionError):
                extract_pdf_text(source, policy=ExtractionPolicy(max_pages=1))

    def test_json_sidecar_is_separate_and_readable(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "law.pdf"
            make_pdf(source, ["قانون " * 20])
            result = extract_pdf_text(source)
            output = write_extraction_json(result, Path(td) / "extracted" / "text.json")
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["source_sha256"], result.source_sha256)
            self.assertEqual(payload["pages"][0]["page_number"], 1)
            self.assertTrue(source.exists())

    def test_missing_file_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(PDFTextExtractionError):
                extract_pdf_text(Path(td) / "missing.pdf")


if __name__ == "__main__":
    unittest.main()
