import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fitz

from legal_bot.ingestion.policy import ConnectorPolicy
from legal_bot.ingestion.secure_pdf_fetcher import PDFDownloadError, SecurePDFDownloader


class FakeResponse:
    def __init__(self, data=b"", status=200, headers=None):
        self.status_code = status
        self.headers = headers or {"Content-Type": "application/pdf", "Content-Length": str(len(data))}
        self.data = data
        self.closed = False
    def iter_content(self, chunk_size=65536):
        for i in range(0, len(self.data), chunk_size):
            yield self.data[i:i + chunk_size]
    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, response): self.response = response
    def get(self, *args, **kwargs):
        assert kwargs["allow_redirects"] is False
        assert kwargs["verify"] is True
        return self.response


def sample_pdf():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "MACHINA test")
    data = doc.tobytes()
    doc.close()
    return data


class SecurePDFFetcherTests(unittest.TestCase):
    def make_downloader(self, td, data, *, allowed=True, max_bytes=2_000_000, status=200, headers=None):
        policy = ConnectorPolicy(allow_downloads=allowed, max_asset_bytes=max_bytes)
        response = FakeResponse(data, status=status, headers=headers)
        return SecurePDFDownloader(Path(td) / "pdf", allowed_hosts={"www.ekhtebar.ir"},
                                   policy=policy, session=FakeSession(response)), response

    @patch("legal_bot.ingestion.secure_pdf_fetcher._public_host")
    def test_download_valid_pdf_and_hash_named_immutable_file(self, dns):
        with tempfile.TemporaryDirectory() as td:
            data = sample_pdf()
            downloader, response = self.make_downloader(td, data)
            result = downloader.download("https://www.ekhtebar.ir/sample.pdf")
            self.assertEqual(result.size_bytes, len(data))
            self.assertEqual(result.page_count, 1)
            self.assertTrue(Path(result.path).exists())
            self.assertEqual(Path(result.path).read_bytes(), data)
            self.assertEqual(Path(result.path).name, result.sha256 + ".pdf")
            self.assertTrue(response.closed)

    def test_downloads_disabled_by_default(self):
        with tempfile.TemporaryDirectory() as td:
            downloader, _ = self.make_downloader(td, sample_pdf(), allowed=False)
            with self.assertRaises(PDFDownloadError):
                downloader.download("https://www.ekhtebar.ir/sample.pdf")

    @patch("legal_bot.ingestion.secure_pdf_fetcher._public_host")
    def test_rejects_html_or_fake_pdf(self, dns):
        with tempfile.TemporaryDirectory() as td:
            downloader, _ = self.make_downloader(td, b"<html>not pdf</html>")
            with self.assertRaises(PDFDownloadError):
                downloader.download("https://www.ekhtebar.ir/fake.pdf")

    @patch("legal_bot.ingestion.secure_pdf_fetcher._public_host")
    def test_rejects_oversized_response(self, dns):
        with tempfile.TemporaryDirectory() as td:
            downloader, _ = self.make_downloader(td, b"%PDF-" + b"x" * 100, max_bytes=32)
            with self.assertRaises(PDFDownloadError):
                downloader.download("https://www.ekhtebar.ir/large.pdf")

    @patch("legal_bot.ingestion.secure_pdf_fetcher._public_host")
    def test_rejects_non_success_status(self, dns):
        with tempfile.TemporaryDirectory() as td:
            downloader, _ = self.make_downloader(td, b"", status=403)
            with self.assertRaises(PDFDownloadError):
                downloader.download("https://www.ekhtebar.ir/blocked.pdf")

    @patch("legal_bot.ingestion.secure_pdf_fetcher._public_host")
    def test_rejects_unallowlisted_host_before_request(self, dns):
        with tempfile.TemporaryDirectory() as td:
            downloader, _ = self.make_downloader(td, sample_pdf())
            with self.assertRaises(PDFDownloadError):
                downloader.download("https://evil.example/file.pdf")
            dns.assert_not_called()

if __name__ == "__main__":
    unittest.main()
