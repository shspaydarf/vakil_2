# -*- coding: utf-8 -*-
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from legal_bot.ingestion.provenance_validator import validate_document_provenance, write_provenance_report


class ProvenanceValidatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.pdf = self.root / "sample.pdf"
        self.pdf.write_bytes(b"%PDF-1.4\nfixture legal pdf\n%%EOF")
        self.digest = hashlib.sha256(self.pdf.read_bytes()).hexdigest()
        self.candidate = {
            "source_id": "majles_rc", "source_name": "مرکز پژوهش‌های مجلس",
            "page_url": "https://rc.majlis.ir/fa/law/print_version/123",
            "asset_url": "https://rc.majlis.ir/files/law.pdf", "title": "قانون آزمایشی",
        }
        self.download = {
            "source_url": "https://rc.majlis.ir/files/law.pdf", "sha256": self.digest,
            "downloaded_at": "2026-11-01T00:00:00+00:00", "size_bytes": self.pdf.stat().st_size,
        }

    def tearDown(self):
        self.tmp.cleanup()

    def test_consistent_source_and_hash_pass_screening_not_authenticity(self):
        report = validate_document_provenance(self.candidate, self.download, pdf_path=self.pdf)
        self.assertTrue(report.eligible_for_next_review)
        self.assertEqual(report.origin_consistency, "consistent_with_catalog")
        self.assertEqual(report.document_authenticity, "not_proven")
        self.assertEqual(report.checks["pdf_file_hash"], "passed")

    def test_unlisted_host_fails_closed(self):
        bad = dict(self.candidate, asset_url="https://evil.example/law.pdf")
        download = dict(self.download, source_url="https://evil.example/law.pdf")
        report = validate_document_provenance(bad, download)
        self.assertFalse(report.eligible_for_next_review)
        self.assertEqual(report.origin_consistency, "inconsistent")

    def test_unknown_source_fails(self):
        report = validate_document_provenance(dict(self.candidate, source_id="unknown"), self.download)
        self.assertFalse(report.eligible_for_next_review)
        self.assertEqual(report.checks["source_catalog"], "failed")

    def test_pdf_hash_mismatch_fails(self):
        other = self.root / "other.pdf"
        other.write_bytes(b"%PDF-1.4\nchanged\n%%EOF")
        report = validate_document_provenance(self.candidate, self.download, pdf_path=other)
        self.assertFalse(report.eligible_for_next_review)
        self.assertEqual(report.checks["pdf_file_hash"], "failed")

    def test_pipeline_hash_mismatch_fails(self):
        report = validate_document_provenance(self.candidate, self.download,
                                              pipeline_manifest={"source_sha256": "0" * 64})
        self.assertFalse(report.eligible_for_next_review)
        self.assertEqual(report.checks["pipeline_source_hash"], "failed")

    def test_report_is_written_as_sidecar(self):
        report = validate_document_provenance(self.candidate, self.download, pdf_path=self.pdf)
        output = self.root / "provenance_report.json"
        write_provenance_report(report, output)
        self.assertTrue(output.is_file())
        self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["document_authenticity"], "not_proven")
        self.assertTrue(self.pdf.exists())


if __name__ == "__main__":
    unittest.main()
