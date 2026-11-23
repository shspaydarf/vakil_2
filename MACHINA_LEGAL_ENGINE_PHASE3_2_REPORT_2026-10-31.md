# MACHINA — Phase 3.2 Secure PDF Acquisition

**Base:** `MACHINA_Legal_Engine_Phase3_1_Download_Queue_2026-10-31.zip`

## Implemented
- Added `legal_bot/ingestion/secure_pdf_fetcher.py`.
- Kept downloads disabled by default; explicit opt-in is required.
- Added exact-host allowlisting, DNS public-address checks, manual bounded redirects, TLS verification, request timeouts, HTTP/content-type checks, and declared/streamed size limits.
- Added PDF signature/EOF checks and PyMuPDF structural, encryption, and page-count validation.
- Added SHA-256 content-addressed storage with atomic writes and a separate provenance manifest helper.
- Added six focused tests in `tests/test_secure_pdf_fetcher.py` and an operational design note.

## Verification
- Focused ingestion + downloader tests: **11 passed**.
- Full discovered unittest suite: **20 passed, 0 failed**.
- Tests use generated local PDF bytes and mocked HTTP/DNS boundaries; they do **not** establish live access to Majles or Ekhtebar.

## Safety boundary
No live source downloads were run. No PDF was inserted into the active legal JSON bank. No text extraction or OCR was added (those belong to stages 3.3 and 3.4). Existing source connectors and queue behavior were retained.
