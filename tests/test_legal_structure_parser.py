import json
import tempfile
import unittest
from pathlib import Path
from legal_bot.ingestion.legal_structure_parser import (
    LegalStructureError, parse_legal_structure, write_legal_structure_json,
)

class LegalStructureParserTests(unittest.TestCase):
    def test_parses_articles_notes_bands_and_metadata(self):
        pages = [
            {"page_number": 1, "text": "قانون نمونه حمایت از حقوق\nمصوب مجلس شورای اسلامی\nتاریخ تصویب: ۱۴۰۲/۰۵/۱۲\nماده ۱ ـ این قانون برای نمونه است.\nتبصره ۱ ـ حکم تبصره اول.\nالف ـ بند نخست."},
            {"page_number": 2, "text": "ماده ۲ ـ متن ماده دوم.\n۱) جزء اول\nتبصره ـ تبصره بدون شماره."},
        ]
        result = parse_legal_structure(pages, source_sha256="abc", document_type="law")
        self.assertEqual(result.title, "قانون نمونه حمایت از حقوق")
        self.assertEqual(result.issuer, "مصوب مجلس شورای اسلامی")
        self.assertEqual(result.dates["approval_or_issue_date"], "1402/05/12")
        self.assertEqual([a["number"] for a in result.articles], ["1", "2"])
        self.assertEqual(len(result.articles[0]["notes"]), 1)
        self.assertEqual(len(result.articles[0]["bands"]), 1)
        self.assertEqual(result.articles[1]["notes"][0]["label"], "تبصره")
        self.assertEqual(result.articles[1]["start_page"], 2)
        self.assertTrue(result.review_required)

    def test_preserves_ocr_or_extracted_page_provenance(self):
        result = parse_legal_structure([{"page_number": 7, "text": "ماده ۱ ـ متن"}])
        self.assertEqual(result.articles[0]["text_lines"][0]["page_number"], 7)

    def test_flags_duplicate_article_numbers(self):
        result = parse_legal_structure([{"page_number": 1, "text": "ماده ۱ ـ الف\nماده ۱ ـ ب"}])
        self.assertEqual(result.quality["duplicate_article_numbers"], ["1"])

    def test_no_text_rejected(self):
        with self.assertRaises(LegalStructureError):
            parse_legal_structure([{"page_number": 1, "text": "  "}])

    def test_writes_separate_sidecar(self):
        result = parse_legal_structure([{"page_number": 1, "text": "ماده ۱ ـ متن"}])
        with tempfile.TemporaryDirectory() as td:
            target = write_legal_structure_json(result, Path(td) / "stage" / "structure.json")
            payload = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(payload["parser_version"], "3.5.0")
            self.assertTrue(payload["review_required"])

if __name__ == "__main__":
    unittest.main()
