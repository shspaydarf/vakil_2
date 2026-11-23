# Phase 7.8 — Human-approved isolated staging and search evaluation

## Scope

Phase 7.8 evaluates one already-staged candidate using the existing legal-search
scoring primitives. It requires a matching Phase 7.7 review packet and a valid
hash-chained decision ledger whose latest event is `approved_for_staging`.

The review approval is bound to the candidate's `catalog_document_id` (or its
`candidate_id` when no catalog ID is supplied), the review ID, and the exact
packet SHA-256. A later `needs_correction` or `rejected` event invalidates the
staging approval for this evaluation.

## Evaluation

- Runs the existing isolated staged-package preview.
- Reports per-query hits and source-page references.
- When human-curated expected record IDs are supplied, computes precision@k,
  recall@k, reciprocal rank, and nDCG@k.
- When expected labels are absent, relevance metrics remain `null`; the report
  explicitly records that relevance was not assessed.
- Fingerprints the four active JSON banks before and after evaluation and
  compares active-search results before and after.
- Writes an optional JSON report atomically to a caller-selected path.

## Safety invariants

- No network access or downloads.
- No insertion into the active corpus or production search index.
- No active JSON bank writes.
- Candidate hits remain labelled `staging_only_not_active`.
- The 7.7 approval means ingestion-data-quality review only; it does not
  establish authenticity, official authority, current force, amendment, repeal,
  or any other legal effect.
- The report does not authorize a Phase 5.7 transaction commit or production
  activation.

## Test boundary

Automated tests use synthetic package and review fixtures. They verify software
behavior and isolation safeguards, not the legal correctness of any real Iranian
law or the reachability of Parliament's live document repository.
