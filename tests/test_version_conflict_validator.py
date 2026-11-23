# -*- coding: utf-8 -*-
import json
import tempfile
import unittest
from pathlib import Path
from legal_bot.ingestion.version_conflict_validator import (
    compare_legal_document_versions, write_version_conflict_report,
)


def doc(doc_id, text, date="1400/01/01", articles=None):
    return {
        "document_id": doc_id,
        "metadata": {"document_type": "قانون", "title": "قانون نمونه", "issuer": "مجلس", "number": "۱۲۳", "date": date},
        "normalized_text": text,
        "structure": {"articles": articles or []},
    }


class VersionConflictValidatorTests(unittest.TestCase):
    def test_exact_duplicate_candidate(self):
        report = compare_legal_document_versions([doc("a", "متن قانون"), doc("b", "متن قانون")])
        self.assertEqual(report.comparisons[0]["relationship"], "exact_duplicate_candidate")
        self.assertFalse(report.legal_amendment_proven)

    def test_same_identity_different_text_and_article_diff(self):
        a = doc("old", "متن قدیمی", "1398/01/01", [{"number": "۱", "text": "متن قدیم"}])
        b = doc("new", "متن جدید", "1402/01/01", [{"number": "۱", "text": "متن جدید"}, {"number": "۲", "text": "ماده دوم"}])
        report = compare_legal_document_versions([a, b])
        pair = report.comparisons[0]
        self.assertEqual(pair["relationship"], "same_identity_different_text_candidate")
        self.assertEqual(pair["article_differences"]["only_in_b"], ["2"])
        self.assertEqual(len(pair["article_differences"]["changed"]), 1)

    def test_near_duplicate_without_matching_identity(self):
        a = {"id": "a", "title": "عنوان الف", "text": "این یک متن حقوقی نسبتاً طولانی برای آزمایش شباهت اسناد است."}
        b = {"id": "b", "title": "عنوان ب", "text": "این یک متن حقوقی نسبتاً طولانی برای آزمایش شباهت اسناد است!"}
        report = compare_legal_document_versions([a, b], near_duplicate_threshold=0.9)
        self.assertEqual(report.comparisons[0]["relationship"], "near_duplicate_candidate")

    def test_unrelated_documents_do_not_match(self):
        report = compare_legal_document_versions([
            {"id": "a", "title": "الف", "text": "متن کاملاً متفاوت اول"},
            {"id": "b", "title": "ب", "text": "محتوای نامرتبط دوم"},
        ])
        self.assertEqual(report.status, "no_candidate_relationship_detected")

    def test_report_written_atomically(self):
        report = compare_legal_document_versions([doc("a", "متن"), doc("b", "متن")])
        with tempfile.TemporaryDirectory() as td:
            path = write_version_conflict_report(report, Path(td) / "version_report.json")
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["validator_version"], "4.4.0")
            self.assertFalse(saved["active_bank_changed"])

    def test_invalid_threshold_rejected(self):
        with self.assertRaises(ValueError):
            compare_legal_document_versions([], near_duplicate_threshold=0.2)


if __name__ == "__main__":
    unittest.main()
