import unittest
import fitz
from legal_bot.ingestion.dotic_pdf_validator import PDFValidationError, validate_pdf_bytes


def make_pdf():
    doc = fitz.open(); doc.new_page(); data = doc.tobytes(); doc.close(); return data

class DoticPDFValidatorTests(unittest.TestCase):
    def test_valid_pdf_returns_hash_and_no_bank_write(self):
        report = validate_pdf_bytes(make_pdf(), "https://dotic.ir/files/law.pdf")
        self.assertEqual(report["technical_pdf_validation"], "passed")
        self.assertEqual(len(report["sha256"]), 64)
        self.assertFalse(report["active_bank_write"])

    def test_rejects_html_with_pdf_name(self):
        with self.assertRaises(PDFValidationError):
            validate_pdf_bytes(b"<html>error</html>", "https://dotic.ir/error.pdf")

    def test_rejects_truncated_pdf(self):
        with self.assertRaises(PDFValidationError):
            validate_pdf_bytes(b"%PDF-1.4\nnot finished", "https://dotic.ir/a.pdf")

    def test_rejects_oversized_file(self):
        with self.assertRaises(PDFValidationError):
            validate_pdf_bytes(make_pdf(), "https://dotic.ir/a.pdf", max_bytes=10)

    def test_rejects_external_source_host(self):
        with self.assertRaises(PDFValidationError):
            validate_pdf_bytes(make_pdf(), "https://evil.example/a.pdf")

    def test_rejects_nonstandard_port(self):
        with self.assertRaises(PDFValidationError):
            validate_pdf_bytes(make_pdf(), "https://dotic.ir:8443/a.pdf")

if __name__ == "__main__": unittest.main()
