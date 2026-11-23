# Phase 5.7 — Controlled Human-Gated Import

## Scope

Phase 5.7 adds the final controlled activation gate for staged candidates. It
supports only the four whitelisted production JSON targets identified in Phase
5.1. It does **not** automatically convert OCR/extracted records into legacy
bank rows: the caller must provide a complete, schema-compatible replacement
payload after reviewing the mapping. This avoids silently guessing legacy
field semantics.

## Two-step workflow

1. `prepare_staged_import(...)` requires a package physically inside the staging
   directory, its unchanged pending package state, the saved Phase 4.6 final
   validation report with `phase5_eligible=true`, and a complete human review
   record covering source, legal, and mapping review. It checks the document
   kind/target pairing, production JSON shape, presence of every extracted
   record text, and append-only preservation of all existing records/metadata.
   It then calls the Phase 5.4 dry-run transaction preparer and writes
   `phase5_7_import_gate.json`. Active bank files remain untouched.
2. `commit_staged_import(...)` requires a second explicit `explicit_commit=True`
   plus the exact same complete human approval record. It delegates the actual
   write to the existing locked, hash-guarded, backed-up transaction engine.

Example API:

```python
from legal_bot.ingestion.controlled_import import (
    prepare_staged_import, commit_staged_import,
)

prepared = prepare_staged_import(
    staging_package_path,
    {"laws.json": reviewed_full_laws_payload},
    transaction_id="legal-import-2026-001",
    human_approval={
        "approved": True, "reviewer_id": "reviewer-17",
        "decided_at": "2026-11-01T12:00:00+00:00",
        "source_review_completed": "true",
        "legal_review_completed": "true",
        "mapping_review_completed": "true",
    },
)
# Review the generated transaction manifest/diff before the separate commit:
result = commit_staged_import(
    "legal-import-2026-001", human_approval=approval, explicit_commit=True,
)
```

## Safety boundaries

- Preparation is dry-run and does not write active bank files.
- Only the target appropriate to the candidate document kind is accepted.
- Existing records and metadata must remain present and unchanged (append-only).
- The extracted text of every candidate record must appear in the proposed payload.
- A separate second explicit commit is required; the approval must match the prepared gate.
- The transaction engine rechecks active-file hashes, uses an exclusive writer lock,
  stores byte-exact backups, and journals the commit.
- This software gate does not establish source authenticity, legal validity,
  amendment/repeal status, or current force of law. Those remain human/legal review.
- No live downloads or automatic activation are enabled.

## Verification

Automated tests use temporary fixture banks only. They cover missing approvals,
append-only violations, target mismatch, missing candidate text, failed Phase 4.6
gate, path escape, second confirmation, approval mismatch, and successful
transactional commit. The real active bank is not modified by these tests.
