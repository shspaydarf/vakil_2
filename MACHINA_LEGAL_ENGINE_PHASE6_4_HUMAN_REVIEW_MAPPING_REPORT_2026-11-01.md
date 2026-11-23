# MACHINA Legal Engine — Phase 6.4 Report

## Scope
Implemented a fail-closed human-review packet and explicit bank-schema mapping workflow. Phase 6.4 does not perform legal interpretation, establish current force, or write to the active JSON bank.

## Added
- `legal_bot/ingestion/human_review_mapping.py`
  - Creates a review packet only when Phase 6.3 technical integrity passed, the original PDF exists, mirror fallback was not used, and extracted structure is supplied.
  - Records the original PDF hash and a deterministic hash of the extracted structure.
  - Requires an attributable reviewer decision, confirmation of comparison against the original PDF, and reviewed page ranges.
  - Requires explicit target collection, field map, record mappings, matching reviewer identity, and explicit no-overwrite/no-drop declarations before an approval can be recorded.
  - Never writes to active bank files.
- `tests/test_human_review_mapping.py`: five tests covering blocked packet creation, readiness prerequisites, missing mapping, valid review/mapping, and overwrite/drop prevention.

## Real-document status
The selected document remains **blocked for substantive human review** because the Phase 6.2 acquisition did not produce a verified PDF from `rc.majlis.ir`; Phase 6.3 therefore has not passed on the real selected document. Search results surfaced a 31-page copy on FAOLEX, but this is a secondary host and is not accepted as the official source under project policy. No OCR, extraction, legal comparison, or actual record mapping was performed on that copy.

The official Parliament record page is `https://rc.majlis.ir/fa/law/print_version/1014070`; a direct official PDF asset endpoint remains unresolved.

## Tests
- New Phase 6.4 tests: 5 passed.
- Full project suite: 585 passed in 15.13 seconds.
- `python -m compileall -q legal_bot tests`: passed.
- Active bank files: not modified by this phase.

## Limitations
A successful test suite validates software behavior, not the legal accuracy of the selected law. Human review and bank mapping remain pending until the original official PDF is acquired, technically validated, and its extracted structure is available for page-by-page comparison.
