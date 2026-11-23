# MACHINA Search Stage 1 — Multi-document search engine

## Changes
- Added `search_case_documents` to `legal_bot/analysis.py`.
- Case search now searches each authorized stored document independently instead of searching one concatenated case text.
- Each hit retains document id, filename, extracted page number when available, matched line and surrounding snippet.
- Empty extracted documents are skipped; results are bounded globally and per document.
- Updated the existing case-search handler to retrieve documents through `get_case_documents(uid, cid)`, whose SQL join enforces case ownership, and pass those documents to the new search function.
- Updated result formatting to show source filename, page (or unknown), and document id.
- Added four focused tests in `tests/test_case_document_search.py`.

## Validation
- `pytest -q`: 148 passed in 13.89s.
- `python -m compileall -q legal_bot tests`: passed.

## Scope and limitations
- No database schema, law JSON, Gramophone, or original uploaded-file handling changes.
- Search uses locally stored extracted text only; no original documents are sent to external AI services.
- Exact page numbers are shown only when present in extracted page markers. Legacy text without markers retains the search helper's fallback page behavior and should not be interpreted as verified pagination.
- This stage implements the search engine/provenance layer. Dedicated Mini App/UI refinements remain Stage 2.
- Live Telegram deployment and production-scale performance were not tested.
