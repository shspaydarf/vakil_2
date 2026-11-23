# MACHINA Audit — Stage 2: Case Management, Document Upload, and Search

Date: 2026-10-30
Baseline: `LegalBot_MACHINA_Lawyer_Memory_Stage2_Capture_2026-10-30.zip`

## Scope

This pass audited the first functional slice agreed for Stage 2:

1. Case workspace entry and owner-scoped case operations.
2. Mini App document list, upload, deletion, durable storage, and text extraction.
3. Search across extracted text for documents in the selected case.
4. Mini App-to-API request wiring for these flows.

No Telegram classic menu redesign or database schema change was made.

## Critical defect found and fixed

The shared Mini App `api()` helper unconditionally set `Content-Type: application/json` whenever a request had a body. The document upload flow passes a browser `FormData` object. Overriding the browser-generated multipart header prevents the browser from attaching the required multipart boundary, so the API's multipart parser rejects real Mini App uploads.

Fix:
- Detect `FormData` bodies in the shared API helper.
- Do not set `Content-Type` for `FormData`; allow `fetch` to generate `multipart/form-data; boundary=...`.
- Keep `application/json` for ordinary JSON request bodies.
- Clear the file input after capturing its selected files, allowing the same file to be selected again after an upload attempt.

Regression verification:
- Added a test asserting the FormData handling contract.
- Added a multipart endpoint test that passes a real multipart body through the API upload parser and verifies the temporary file content and response.
- Ran a Node smoke test with a real `FormData` instance and a stubbed `fetch`; verified that no explicit Content-Type is attached.

## Verified behavior

- Case/document access is scoped using the authenticated user ID and case ID; client-supplied user IDs are not used by the Mini App request contract.
- Document listing uses the case owner relationship.
- Document ingestion rejects missing/archived cases, empty files, unsupported suffixes, mismatched file signatures for PDF/DOCX/JPEG/PNG/WebP, and files from which no usable text can be extracted.
- Files are copied to durable case storage with a generated storage filename and SHA-256 metadata.
- Registration/storage failures have compensating cleanup paths.
- Multi-file Mini App ingestion rolls back files already ingested if a later file in the same batch fails.
- Document deletion checks owner/case membership and removes the registered stored file where possible.
- PDF extraction is page-limited; image and scanned-PDF extraction paths use OCR where required and available.
- Search is scoped to the selected authenticated user's case, uses extracted text only, and returns document/page provenance.
- Search input is bounded to 200 characters; results are bounded to 60 total and 12 per document.
- The Mini App contains the document picker, upload button, document list, delete action, search form, result groups, and source/page snippets.
- These controls use existing Mini App button/card styles and the shared API helper; they are not Telegram callback-only controls.

## Current operational limits and caveats

- Per-file upload limit: configured up to 20 MB.
- Aggregate HTTP request limit: configured default 25 MB (environment-bounded up to 64 MB).
- Batch file count: configured by `MAX_CASE_ADDITION_FILES` (default follows the album limit, currently 20).
- Later document additions are limited by the configured number of addition sessions (default 8).
- Search covers extracted text only. Scanned or low-quality documents may be absent when OCR fails or returns no usable text. The UI/API explicitly communicates this limitation.
- Search has a fixed bounded result set and no pagination in this version.
- File signature checks are not a malware scanner; no antivirus scanning is claimed.
- The API route/parser and client request helper were tested locally, but deployment behind the production reverse proxy and a live Telegram WebView upload have not been exercised in this environment.

## Test results after fix

- `pytest -q`: **185 passed**.
- `node --check miniapp/app.js`: passed.
- Python `compileall`: passed.
- `preflight.py`: passed.
- Node FormData header smoke test: passed.
- ZIP integrity: checked after packaging.

## Stage 2 status

The first Stage 2 slice (case management/document upload/document search) is functionally audited and the critical Mini App upload-header defect is fixed. This does not mean all MACHINA features have completed Stage 2; multi-document analysis, workflow agent, AI/drafting, and the remaining integrated features still require their own end-to-end functional checks in the following Stage 2 passes.
