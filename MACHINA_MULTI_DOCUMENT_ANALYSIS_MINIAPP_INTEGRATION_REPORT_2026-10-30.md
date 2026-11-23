# MACHINA — Multi-document analysis integration

## Delivered
- Expanded the deterministic multi-document analysis result with document coverage summaries, extracted-fact counts, cross-document same-value matches, and date/amount comparison candidates.
- Preserved document provenance (document ID, file name, page when available, verbatim value, snippet, and confidence).
- Added an authenticated `GET /api/v1/cases/{case_id}/document-analysis` endpoint.
- The endpoint verifies case ownership and obtains documents only through `DocumentService.list(authenticated_user_id, case_id)`. It accepts no client-supplied document IDs or arbitrary document scope.
- Added a Mini App workspace card and a dedicated analysis view showing coverage, shared values, differences requiring review, and documents lacking extracted text.
- Kept the engine deterministic and local; no external AI request, schema migration, or original-file transfer was added.

## Safety and interpretation
- Different dates or amounts are surfaced only as comparison candidates, never automatically labelled contradictions.
- Same-value matches are not proof that two references concern the same event or obligation.
- All extracted facts remain unverified and require lawyer review against the original documents.
- Scanned or otherwise textless documents are explicitly reported as skipped; OCR is not silently assumed to have happened.
- The current comparison scope is limited to normalized dates and amounts. It is not semantic contradiction detection and does not make legal conclusions.
- Analysis is computed on request and is not persisted as a workflow checkpoint in this delivery.

## Verification
- `pytest -q`: 168 passed.
- `python -m compileall -q legal_bot`: passed.
- `node --check miniapp/app.js`: passed.
- ZIP integrity check: performed after packaging.
- Live Telegram/production-server validation: not performed in this environment.
