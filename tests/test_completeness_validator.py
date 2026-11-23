# -*- coding: utf-8 -*-
import json
import tempfile
import unittest
from pathlib import Path
from legal_bot.ingestion.completeness_validator import validate_document_completeness, write_completeness_report

class CompletenessValidatorTests(unittest.TestCase):
    def test_clean_sequential_document_is_screened_not_proven(self):
        report = validate_document_completeness(
            [{"page_number": 1, "text": "ماده ۱"}, {"page_number": 2, "text": "ماده ۲"}],
            {"articles": [{"number": "۱", "start_page": 1, "end_page": 1},
                          {"number": "۲", "start_page": 2, "end_page": 2}]},
            expected_page_count=2)
        self.assertEqual(report.status, "screening_no_anomaly_detected")
        self.assertFalse(report.completeness_proven)
        self.assertTrue(report.review_required)

    def test_page_gap_and_duplicate_are_high_severity(self):
        report = validate_document_completeness(
            [{"page_number": 1, "text": "الف"}, {"page_number": 3, "text": "ب"}, {"page_number": 3, "text": "ج"}])
        codes = {f["code"] for f in report.findings}
        self.assertIn("page_sequence_anomaly", codes)
        self.assertEqual(report.status, "critical_anomalies_found")

    def test_empty_page_flagged(self):
        report = validate_document_completeness([{"page_number": 1, "text": ""}])
        self.assertIn("empty_text_pages", {f["code"] for f in report.findings})

    def test_article_number_gap_is_only_review(self):
        report = validate_document_completeness(
            [{"page_number": 1, "text": "متن"}],
            {"articles": [{"number": "۱", "start_page": 1, "end_page": 1},
                          {"number": "۳", "start_page": 1, "end_page": 1}]})
        self.assertEqual(report.status, "review_recommended")
        self.assertIn("possible_missing_articles", {f["code"] for f in report.findings})

    def test_duplicate_article_and_note(self):
        report = validate_document_completeness(
            [{"page_number": 1, "text": "متن"}],
            {"articles": [{"number": "۱", "start_page": 1, "end_page": 1,
                           "notes": [{"number": "۱"}, {"number": "۱"}]},
                          {"number": "۱", "start_page": 1, "end_page": 1}]})
        codes = {f["code"] for f in report.findings}
        self.assertIn("duplicate_article_numbers", codes)
        self.assertIn("duplicate_note_numbers", codes)

    def test_ocr_confidence_and_page_count(self):
        report = validate_document_completeness(
            [{"page_number": 1, "text": "متن", "ocr_mean_confidence": 20}], expected_page_count=2)
        self.assertIn("page_count_mismatch", {f["code"] for f in report.findings})
        self.assertIn("low_ocr_confidence", {f["code"] for f in report.findings})

    def test_report_written_atomically_as_json(self):
        report = validate_document_completeness([{"page_number": 1, "text": "متن"}])
        with tempfile.TemporaryDirectory() as td:
            path = write_completeness_report(report, Path(td) / "completeness.json")
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["validator_version"], "4.3.0")

if __name__ == "__main__":
    unittest.main()
