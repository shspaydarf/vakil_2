import json
import tempfile
import unittest
from pathlib import Path
from legal_bot.ingestion.models import CandidateDocument
from legal_bot.ingestion.policy import host_allowed, classify_http_response
from legal_bot.ingestion.registry import StagingRegistry
from legal_bot.ingestion.download_queue import DownloadQueue

class IngestionArchitectureTests(unittest.TestCase):
    def candidate(self):
        return CandidateDocument(source_id="ekhtebar", source_name="اختبار",
            source_role="secondary_discovery", document_type="supreme_court_ruling",
            title="نمونه رأی", page_url="https://www.ekhtebar.ir/archive/1",
            asset_url="https://www.ekhtebar.ir/files/1.pdf")

    def test_exact_host_allowlist(self):
        self.assertTrue(host_allowed("https://www.ekhtebar.ir/a", {"www.ekhtebar.ir"}))
        self.assertFalse(host_allowed("https://www.ekhtebar.ir.evil.test/a", {"www.ekhtebar.ir"}))
        self.assertFalse(host_allowed("file:///etc/passwd", {"www.ekhtebar.ir"}))

    def test_challenge_and_rate_limit_classification(self):
        self.assertEqual(classify_http_response(403, "text/html", "captcha"), "access_challenge")
        self.assertEqual(classify_http_response(429, "text/html"), "retry_later")
        self.assertEqual(classify_http_response(502, "text/html"), "source_unavailable")

    def test_registry_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            registry = StagingRegistry(Path(td) / "ingestion_registry.json")
            first = registry.add_candidates([self.candidate()])
            second = registry.add_candidates([self.candidate()])
            payload = json.loads((Path(td) / "ingestion_registry.json").read_text(encoding="utf-8"))
            self.assertEqual(first["added"], 1)
            self.assertEqual(second["added"], 0)
            self.assertEqual(len(payload["records"]), 1)

    def test_download_queue_is_bounded_idempotent_and_allowlisted(self):
        with tempfile.TemporaryDirectory() as td:
            queue = DownloadQueue(Path(td) / "download_queue.json",
                allowed_hosts={"www.ekhtebar.ir"}, max_queue_items=1)
            first = queue.enqueue([self.candidate()])
            second = queue.enqueue([self.candidate()])
            self.assertEqual(first["added"], 1)
            self.assertEqual(second["duplicates_skipped"], 1)
            self.assertEqual(len(queue.list_items(state="queued")), 1)
            bad = CandidateDocument(source_id="x", source_name="x", source_role="x",
                document_type="law", title="bad", page_url="https://x.test",
                asset_url="https://evil.test/file.pdf")
            self.assertEqual(queue.enqueue([bad])["rejected"], 1)

    def test_download_queue_retry_limit(self):
        with tempfile.TemporaryDirectory() as td:
            queue = DownloadQueue(Path(td) / "download_queue.json",
                allowed_hosts={"www.ekhtebar.ir"})
            queue.enqueue([self.candidate()])
            key = queue.list_items()[0]["candidate_key"]
            self.assertTrue(queue.mark_result(key, success=False, error="network"))
            self.assertEqual(queue.list_items()[0]["state"], "retry_wait")
            queue.mark_result(key, success=False, error="network")
            queue.mark_result(key, success=False, error="network")
            self.assertEqual(queue.list_items()[0]["state"], "failed")
            self.assertEqual(queue.list_items()[0]["attempt_count"], 3)

if __name__ == "__main__":
    unittest.main()
