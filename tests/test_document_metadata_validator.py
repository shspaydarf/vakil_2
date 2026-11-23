# -*- coding: utf-8 -*-
import unittest
from legal_bot.ingestion.document_metadata_validator import validate_document_metadata


class DocumentMetadataValidatorTests(unittest.TestCase):
    def test_consistent_metadata_screen_passes_without_authenticating(self):
        report = validate_document_metadata(
            {"document_type": "قانون", "title": "قانون نمونه", "issuer": "مجلس شورای اسلامی",
             "document_number": "۱۲۳", "enactment_date": "1402/02/10"},
            {"title": "قانون نمونه", "issuer": "مجلس شورای اسلامی", "document_number": "123",
             "enactment_date": "1402-02-10"})
        self.assertEqual(report.checks["title_agreement"], "consistent_across_available_sources")
        self.assertEqual(report.overall_status, "screening_passed")
        self.assertEqual(report.legal_authenticity, "not_proven")

    def test_title_conflict_detected(self):
        report = validate_document_metadata({"title": "قانون الف"}, {"title": "قانون ب"})
        self.assertEqual(report.checks["title_agreement"], "conflict")
        self.assertEqual(report.overall_status, "conflict_detected")

    def test_issuer_type_potential_conflict_is_review(self):
        report = validate_document_metadata({"document_type": "قانون", "issuer": "وزارت دادگستری"})
        self.assertEqual(report.checks["issuer_type_compatibility"], "review_required")

    def test_invalid_gregorian_date_detected(self):
        report = validate_document_metadata({"publication_date": "2025-02-30"})
        self.assertEqual(report.checks["publication_date_format"], "invalid")

    def test_invalid_jalali_month_detected(self):
        report = validate_document_metadata({"document_date": "1402/13/01"})
        self.assertEqual(report.checks["document_date_format"], "invalid")

    def test_unrecognized_date_is_not_guessed(self):
        report = validate_document_metadata({"document_date": "اول خرداد ۱۴۰۲"})
        self.assertEqual(report.checks["document_date_format"], "unrecognized")

    def test_date_conflict_detected(self):
        report = validate_document_metadata({"enactment_date": "1401/01/01"},
                                            {"enactment_date": "1401/01/02"})
        self.assertEqual(report.checks["enactment_date_agreement"], "conflict")

    def test_missing_fields_remain_missing(self):
        report = validate_document_metadata({})
        self.assertIsNone(report.normalized_metadata["title"])
        self.assertEqual(report.checks["title_presence"], "missing")

    def test_date_chronology_flagged(self):
        report = validate_document_metadata({"enactment_date": "1402/05/01", "publication_date": "1402/04/01"})
        self.assertEqual(report.checks["chronology_enactment_date_publication_date"], "review_required")

    def test_report_serializes(self):
        report = validate_document_metadata({"title": "قانون"})
        self.assertIn("findings", report.to_dict())


if __name__ == "__main__":
    unittest.main()
