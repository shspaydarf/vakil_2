import json
import tempfile
import unittest
from pathlib import Path

from legal_bot.ingestion.legal_text_normalizer import (
    NormalizationPolicy, normalize_persian_text, normalize_legal_document,
    write_normalization_json,
)

class PersianLegalTextNormalizerTests(unittest.TestCase):
    def test_arabic_characters_and_digits_normalized(self):
        self.assertEqual(normalize_persian_text("ماده ۱۲ ـ كليه يک").replace("يک", "یک"), "ماده ۱۲ ـ کلیه یک")

    def test_original_text_is_preserved_verbatim(self):
        raw = "ماده 1\nكليه حقوق محفوظ است"
        result = normalize_legal_document([{"page_number": 1, "text": raw}])
        self.assertEqual(result.pages[0]["raw_text"], raw)
        self.assertNotEqual(result.pages[0]["raw_text"], result.pages[0]["normalized_text"])

    def test_page_numbers_and_provenance_preserved(self):
        result = normalize_legal_document([
            {"page_number": 4, "text": "ماده ۱ متن قانون", "provenance": "tesseract_ocr"}
        ])
        self.assertEqual(result.pages[0]["page_number"], 4)
        self.assertEqual(result.pages[0]["provenance"], "tesseract_ocr")

    def test_no_content_deletion_or_default_punctuation_collapse(self):
        raw = "ماده ۱: متن... (الف)؛ تبصره ۲"
        result = normalize_legal_document([{"page_number": 1, "text": raw}])
        self.assertIn("متن...", result.pages[0]["normalized_text"])
        self.assertIn("تبصره ۲", result.pages[0]["normalized_text"])

    def test_structure_copy_normalized_without_mutating_input(self):
        structure = {"articles": [{"number": "1", "text_lines": [{"text": "كليه موارد"}]}]}
        result = normalize_legal_document([{"page_number": 1, "text": "قانون"}], structure=structure)
        self.assertEqual(structure["articles"][0]["text_lines"][0]["text"], "كليه موارد")
        normalized = result.quality["normalized_structure"]
        self.assertEqual(normalized["articles"][0]["text_lines"][0]["text"], "کلیه موارد")

    def test_empty_pages_rejected(self):
        with self.assertRaises(ValueError):
            normalize_legal_document([])

    def test_atomic_json_sidecar(self):
        result = normalize_legal_document([{"page_number": 1, "text": "قانون شماره 1"}])
        with tempfile.TemporaryDirectory() as tmp:
            target = write_normalization_json(result, Path(tmp) / "normalized.json")
            data = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(data["normalizer_version"], "3.6.0")
            self.assertTrue(data["review_required"])

if __name__ == "__main__":
    unittest.main()
