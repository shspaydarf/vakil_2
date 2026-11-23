# MACHINA Phase 10.2.3 — PDF Acquisition, Extraction and OCR Staging

## Delivered
- Added `legal_bot/ingestion/staged_pdf_processor.py` as a page-budgeted, resumable staging processor.
- Reuses the existing fail-closed `SecurePDFDownloader` through `acquire_pdf`; the downloaded original remains immutable and its provenance manifest is stored separately.
- Extracts text page-by-page in batches capped at 20 pages per invocation.
- Selects sparse/scanned pages for Persian OCR only; OCR output is explicitly machine-generated and remains separate from source text.
- Persists a SHA-256-bound progress sidecar atomically. A changed PDF cannot resume against stale progress.
- Does not import or modify active JSON banks.

## Validation
- Added 3 tests for 20-page batching/resume, source-hash mismatch rejection, and hard page-budget enforcement.
- Full suite: **746 passed**.
- `python -m compileall -q legal_bot tests`: passed.
- Network access was not attempted; live source download and real Tesseract Persian OCR remain unverified in this environment.
- Active legal-bank files are expected to remain unchanged; verified separately against the Phase 10.2.2 baseline.

## Important boundary
This completes a reusable staged PDF-processing component, not the full production connection from the live source crawler through downloader, extraction, OCR, validation and import. OCR pages with low confidence remain review-required; this phase does not certify legal completeness or validity.
