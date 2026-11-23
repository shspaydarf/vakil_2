# MACHINA Legal Engine — Phase 6.5

## Scope

Phase 6.5 adds an isolated evaluation layer for staged-candidate retrieval. It uses the existing production retrieval scoring primitives through `legal_search_preview.py`, but keeps staged records outside the active corpus and search index.

## Implementation

- Added `legal_bot/ingestion/phase6_5_evaluation.py`.
- Added query-level hit counts and optional expected-record recall measurement.
- Checks source-page references and staging-only labels on returned hits.
- Fingerprints the four active JSON bank files before and after preview.
- Compares active search results before and after preview.
- Produces an auditable JSON report; output is atomic.
- Real-document readiness is fail-closed and requires technical validation of the official PDF plus a recorded human review and explicit mapping.
- The evaluator never commits an import and never asserts legal authenticity or current legal force.

## Tests

- Four new tests cover staged retrieval, expected-record recall, missing human review, empty queries, report persistence, and non-mutation guarantees.
- Full project suite: **589 passed**.
- `compileall`: successful.

## Real selected statute status

The selected statute still has no acquired official PDF. The Phase 6.2 acquisition manifest records `official_pdf_asset_url_unresolved`; Phase 6.3 records `blocked_pending_official_pdf`. Therefore a real-document search evaluation could not honestly be performed in this phase. The status is recorded in:

`legal_bot/data/iran/ingestion/test_candidates/phase6_5_real_document_status.json`

Synthetic fixtures validate software behavior only. They are not evidence about the selected law's text, authenticity, amendments, or current force.

## Safety

- Active bank JSON files unchanged.
- Active search results unchanged in tests.
- No staged record imported.
- No OCR or legal text was fabricated for the real candidate.
- No secondary-source copy was promoted to official source.
