# MACHINA Search Stage 3 — Mini App Integration

## Delivered
- Added authenticated `GET /api/v1/cases/{case_id}/search?q=...`.
- The endpoint first verifies that the case belongs to the authenticated Telegram user, then obtains documents through `DocumentService.list`, whose repository query scopes documents by both case ID and owner ID.
- Search is bounded to 60 hits globally and 12 hits per document; query length is limited to 200 characters.
- Results retain source document ID, filename, extracted page/line locator when available, and surrounding snippet.
- Added a search form to the Mini App's case documents view. Results are grouped by source document and show hit counts, searchable-document coverage, and a reminder to verify the original source.
- Dynamic text is HTML-escaped before rendering. The browser cannot submit arbitrary document IDs or broaden the case scope.
- No database schema or stored document format changes were required.

## Validation
- `pytest -q`: **164 passed**.
- `python -m compileall -q legal_bot tests`: passed.
- `node --check miniapp/app.js`: passed.
- ZIP integrity check: passed after packaging.

## Scope and limitations
- This is a case-wide search over locally extracted document text using the existing deterministic text-search engine. It is not semantic/vector search.
- Scanned files or documents without extracted text may not be searchable. This feature does not introduce OCR or send original documents to an external AI service.
- Page numbers are only as reliable as the page markers present in extracted text; legacy text without verified page markers must not be treated as having precise pagination.
- Automated tests validate API behavior, ownership scoping, UI wiring, and formatting. Live Telegram deployment, real-device rendering, and production-scale load testing remain outstanding.
