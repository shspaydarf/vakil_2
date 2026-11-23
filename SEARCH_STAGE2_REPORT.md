# MACHINA Search Stage 2 — Results Presentation

## Scope
Improved the presentation of the existing multi-document case search. No database schema, law data, Gramophone, or external AI integration changes were made.

## Changes
- Search hits are grouped under their source document instead of being displayed as a flat list.
- The report shows total hit count and number of source documents.
- Each source group shows filename, document ID (when available), and per-document hit count.
- Each hit shows the page and line locator when available, plus the extracted surrounding text.
- Missing page metadata is stated explicitly; no page number is guessed.
- Empty-result output explains that scanned documents or documents without extracted text may not be searchable.
- The report reminds the lawyer to verify the original document before citing a result.
- Existing case menu remains available after the search, including the case-search entry point.

## Validation
- `pytest -q`: 150 passed.
- `python -m compileall -q legal_bot`: passed.
- Two new tests cover document grouping/counts and honest no-result coverage messaging.

## Limitations
- This validates local formatting and project tests, not live Telegram rendering.
- A page number is shown only when extraction provides a page marker. Search still depends on extracted text quality.
