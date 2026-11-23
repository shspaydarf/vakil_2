# Phase 5.6 — Failure Injection and Recovery

## Scope

This phase hardens the Phase 5.4 bank transaction flow against interrupted multi-file commits. It does not import data and does not change the active legal bank during tests.

## New recovery API

`recover_interrupted_transaction(transaction_id, data_dir=...)`

The recovery routine is intentionally fail-closed:

- It accepts only a syntactically safe transaction ID.
- It only examines transactions still marked `prepared_dry_run` (the expected state if a process stopped before the commit manifest was finalized).
- It acquires the same exclusive bank-write lock used by commit.
- Every backup must match the transaction's recorded `before_sha256`.
- A target matching `before_sha256` is treated as untouched.
- A target matching `after_sha256` is restored from its verified backup.
- Any target matching neither hash blocks recovery; it is never overwritten as an unknown concurrent edit.
- All targets are re-hashed after restoration. The manifest and audit log record successful recovery.
- Re-running recovery when no write was interrupted is a no-op.

Example:

```python
from legal_bot.ingestion.bank_transactions import recover_interrupted_transaction

result = recover_interrupted_transaction("tx-2026-001")
```

## Failure-injection coverage

Tests simulate process death after one file of a multi-file transaction has been atomically replaced, with no exception handler or manifest finalization. Additional tests cover no-op recovery, unknown external edits, corrupted backups, an occupied writer lock, and path-traversal transaction IDs.

## Safety boundary

Recovery can identify and reverse a target only when its current bytes match the exact recorded before/after hashes. It cannot reconstruct arbitrary filesystem damage, storage-device failure, or a partially corrupted backup. Those cases stop for manual investigation. The routine is not a substitute for independent backups or filesystem durability guarantees.

## Verification

- Full automated suite: 561 passed.
- `python -m compileall -q legal_bot tests`: passed.
- All four active-bank JSON files remained byte-identical during development and testing; this phase uses temporary test directories for writes.
- No live source downloads and no production-bank import were performed.
