import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import fitz
from legal_bot.ingestion.dotic_pdf_pilot import intake_one_pdf, verify_readiness, PilotIntakeError

class DoticPilotTests(unittest.TestCase):
    def setUp(self):
        doc = fitz.open(); doc.new_page(); self.pdf = doc.tobytes(); doc.close()
        self.network = {"phase":"10.4.2", "sources":[{"source_id":"dotic", "status":"tls_ok_http_not_tested"}]}
        self.source = {"phase":"10.4.3", "source":{"robots_status":"read", "page_status":"ok"}}
    def test_readiness_requires_both_prior_reports(self):
        verify_readiness(self.network, self.source)
        bad = {"phase":"10.4.3", "source":{"robots_status":"unavailable_or_blocked", "page_status":"not_attempted"}}
        with self.assertRaises(PilotIntakeError): verify_readiness(self.network, bad)
    def test_rejects_missing_tls_success(self):
        bad = {"phase":"10.4.2", "sources":[{"source_id":"dotic", "status":"dns_failed"}]}
        with self.assertRaises(PilotIntakeError): verify_readiness(bad, self.source)
    def test_single_pdf_is_quarantined_and_manifest_written(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td)/"candidate.pdf"; source.write_bytes(self.pdf)
            result = intake_one_pdf(source, "https://dotic.ir/files/a.pdf", Path(td)/"quarantine", self.network, self.source)
            self.assertTrue(Path(result["stored_original"]).exists())
            self.assertTrue((Path(td)/"quarantine"/(result["sha256"]+".manifest.json")).exists())
            self.assertFalse(result["active_bank_write"])
            self.assertEqual(result["decision"], "quarantined_candidate_manual_provenance_and_legal_review_required")
    def test_rejects_external_source_url(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td)/"candidate.pdf"; source.write_bytes(self.pdf)
            with self.assertRaises(Exception): intake_one_pdf(source, "https://evil.example/a.pdf", Path(td)/"q", self.network, self.source)
    def test_does_not_overwrite_conflicting_hash_path(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td)/"candidate.pdf"; source.write_bytes(self.pdf)
            q = Path(td)/"q"; q.mkdir(); digest = __import__('hashlib').sha256(self.pdf).hexdigest()
            (q/f"{digest}.pdf").write_bytes(b"different")
            with self.assertRaises(PilotIntakeError): intake_one_pdf(source, "https://dotic.ir/a.pdf", q, self.network, self.source)

if __name__ == "__main__": unittest.main()
