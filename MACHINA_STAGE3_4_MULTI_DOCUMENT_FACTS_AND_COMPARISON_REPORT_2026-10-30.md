# MACHINA — Stages 3 & 4: Multi-document extraction and comparison

## Scope
Implemented a conservative, local, source-linked multi-document analysis service in `legal_bot/cross_document_analysis.py`.

## Stage 3 — structured extraction
- Extracts existing candidate fact types (dates, amounts, identifiers, phone numbers, party/name labels) independently from each document.
- Preserves document ID, file name, page when available, verbatim value, snippet, confidence and review status.
- Reports documents without extracted text rather than silently treating them as empty evidence.
- Reuses `legal_bot.document_facts.extract_document_facts`; no parallel extraction rules or schema migration.

## Stage 4 — cross-document comparison
- Groups normalized date and amount values across distinct documents.
- Emits `comparison_candidate` only when distinct normalized values occur across at least two documents.
- Does not call differences contradictions: distinct values may refer to different events, versions or obligations.
- Every candidate retains source snippets and document provenance and is marked for human review.
- Same-value matches and differences confined to one document are not flagged as cross-document candidates.

## Safety / limitations
- Analysis is deterministic and local; no external LLM call or original-file transfer was added.
- Extracted facts are candidates, not verified facts. No legal conclusion, chronology inference, or contradiction finding is asserted.
- Page numbers are only retained when present in extracted text markers.
- This module is not yet wired into a new Telegram/Mini App screen; presentation/integration remains a later step.
- No database schema, law JSON, or Gramophone changes.

## Verification
- `pytest -q`: 155 passed in 13.94s.
- `python -m compileall -q legal_bot`: passed.
- Added 5 tests in `tests/test_cross_document_analysis.py`.
- Live Telegram and production document validation were not performed.
