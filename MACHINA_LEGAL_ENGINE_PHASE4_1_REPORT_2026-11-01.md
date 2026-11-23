# MACHINA Legal Engine — Phase 4.1 Report

## Delivered

- Added `legal_bot/ingestion/provenance_validator.py`.
- Added six focused tests in `tests/test_provenance_validator.py`.
- Added the phase design and limitation note in
  `legal_bot/ingestion/STAGE4_1_PROVENANCE_VALIDATION.md`.
- The validator checks catalog membership, exact-host allowlists, acquisition
  metadata, SHA-256 format, optional local-file hash, optional Phase 3.7 source
  hash linkage and advisory metadata consistency.
- Output is a separate JSON sidecar. The source PDF, staging registry and
  active legal JSON bank are not modified.

## Safety boundary

The report deliberately distinguishes `origin_consistency` from
`document_authenticity`. Even a fully consistent acquisition chain is not a
cryptographic proof of an official publication or legal validity. The module
always leaves `document_authenticity` as `not_proven` and only offers
`eligible_for_next_review`, never activation approval.

## Verification

See the test results produced for this ZIP build. Tests use local fixtures;
no live source access or legal corpus import was performed.
