# MACHINA Legal Engine — Phase 7.8 Report

**Phase:** 7.8 — Human-approved isolated staging and search evaluation  
**Base:** Phase 7.7 Human Review Gate  
**Date:** 2026-11-01

## Delivered

Added `legal_bot/ingestion/phase7_8_staged_evaluation.py` and its test suite.
The evaluator requires a valid 7.7 review packet and hash-chained ledger,
checks that the latest human decision is a matching `approved_for_staging`,
and binds the approval to the candidate identity and packet hash.

The evaluator calls the existing isolated staged-search preview and reports
per-query retrieval results. If expected record IDs are supplied by a human,
it computes precision@k, recall@k, reciprocal rank, and nDCG@k. If they are not
supplied, relevance metrics remain unassessed rather than being guessed.

It fingerprints the four active JSON banks and compares active-search results
before and after preview. It does not import records, mutate the active index,
access the network, or establish legal validity/current force.

## Validation

- Phase 7.7 baseline suite: **661 passed** (reported by pytest before changes).
- New Phase 7.8 tests: **9 passed**.
- Expected full-suite count: **670 tests**.
- Compile check: recorded in release validation.
- ZIP integrity: recorded in release validation.

The complete suite finished with **670 passed** in 20.98 seconds. The tests use synthetic fixtures and are not evidence of successful live Parliament downloads or legal validation of real documents.

## Protected data

The active banks remain outside the write path of Phase 7.8. The evaluator is
read-only with respect to `laws.json`, `rulings.json`, `consultations.json`, and
`samples_and_circulars.json`. No bank activation or transaction commit occurs.
