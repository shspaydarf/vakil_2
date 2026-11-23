# MACHINA Phase 10.1.2 — Data Contracts and Integration Map

## Result
Defined a shared document envelope and explicit lifecycle contract for the autonomous legal-ingestion pipeline. Added a machine-readable integration map describing current modules, hand-offs, and remaining gaps.

## Implemented
- `legal_bot/ingestion/pipeline_contracts.py`
  - canonical contract version `10.1.2`
  - supported document kinds: law, regulation, supreme-court ruling, administrative-justice ruling, advisory opinion
  - stable identity prefers jurisdiction + issuer + document kind + official number + date; fallback is source-scoped external ID
  - title-only identity is rejected
  - content version key is bound to document ID + SHA-256
  - HTTPS URL shape checks, hash/page-count checks, and explicit lifecycle transitions
- `legal_bot/ingestion/PHASE10_1_2_DATA_CONTRACTS_AND_INTEGRATION_MAP.json`
- `MACHINA_PHASE10_1_2_DATA_CONTRACTS_REPORT_FA.md`
- 8 focused contract tests in `tests/test_pipeline_contracts.py`

## Verification
- Full test suite: **727 passed**.
- `compileall`: passed.
- Active JSON bank hashes: unchanged and match the actual Phase 10.2 source ZIP. During comparison, the prior Phase 10.1.1 inventory metadata was found to contain a malformed 63-character `laws.json` hash; that inventory metadata was corrected to the actual 64-character SHA-256. The active bank file was not changed.
- Network access: not attempted.
- Active bank writes: none.

## Important boundary
This phase defines and tests contracts; it does not claim that all existing modules are now wired end-to-end. The integration map explicitly records the remaining work: official adapters for all document families, persistent seen/cursor and change-detection wiring, scheduler-to-runner orchestration, resumable processing for PDFs exceeding the per-run 20-page budget, safe amendment/partial-repeal update semantics, and production connectivity verification.

## Decision
Phase 10.1.2 is complete as a contract-and-map deliverable. Proceed to 10.1.3: synthetic end-to-end integration tests using the new envelope, without network calls or active-bank mutation.
