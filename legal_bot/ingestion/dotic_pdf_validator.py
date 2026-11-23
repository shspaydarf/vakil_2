# -*- coding: utf-8 -*-
"""Phase 10.4.5: offline validation of a locally supplied Dotic PDF candidate.

This module performs no network access and never writes to staging or active
legal banks. A valid PDF is only a technically valid file, not proof of legal
publication, issuer, authenticity, or current legal status.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ALLOWED_HOSTS = {"dotic.ir", "www.dotic.ir"}

class PDFValidationError(ValueError):
    pass


def validate_pdf_bytes(data: bytes, source_url: str, *, max_bytes: int = 30 * 1024 * 1024,
                       max_pages: int = 2000) -> dict:
    parsed = urlparse(source_url)
    if (parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS
            or parsed.username or parsed.password or parsed.port not in (None, 443)):
        raise PDFValidationError("source_url must be credential-free HTTPS on an allowlisted Dotic host")
    if not isinstance(data, bytes) or len(data) < 16:
        raise PDFValidationError("file is empty or too small to be a PDF")
    if len(data) > max_bytes:
        raise PDFValidationError("file exceeds configured byte limit")
    if not data.startswith(b"%PDF-"):
        raise PDFValidationError("file signature is not PDF; HTML/error pages are rejected")
    if b"%%EOF" not in data[-2048:]:
        raise PDFValidationError("PDF end marker is missing or truncated")
    try:
        import fitz
        doc = fitz.open(stream=data, filetype="pdf")
        try:
            if doc.is_encrypted:
                raise PDFValidationError("encrypted PDFs are not accepted")
            pages = doc.page_count
            if pages < 1 or pages > max_pages:
                raise PDFValidationError("PDF page count is outside configured limits")
            # Force page-tree traversal without extracting or executing embedded content.
            for index in range(pages):
                _ = doc.load_page(index).rect
        finally:
            doc.close()
    except PDFValidationError:
        raise
    except Exception as exc:
        raise PDFValidationError("PDF internal structure could not be validated") from exc
    return {
        "phase": "10.4.5", "source_url": source_url,
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data),
        "page_count": pages, "signature_valid": True, "eof_marker_present": True,
        "encrypted": False, "technical_pdf_validation": "passed",
        "legal_authenticity_verified": False, "legal_status_verified": False,
        "active_bank_write": False, "staging_write": False,
        "decision": "technical_candidate_only_manual_legal_review_required",
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Offline technical validation of a saved Dotic PDF")
    ap.add_argument("--pdf-file", required=True)
    ap.add_argument("--source-url", required=True)
    ap.add_argument("--output", default="/data/ingestion_diagnostics/phase10_4_5_dotic_pdf_validation.json")
    args = ap.parse_args(argv)
    data = Path(args.pdf_file).read_bytes()
    report = validate_pdf_bytes(data, args.source_url)
    target = Path(args.output); target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
