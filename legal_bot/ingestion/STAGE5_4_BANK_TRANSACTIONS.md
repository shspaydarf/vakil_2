# Phase 5.4 — guarded bank transactions

This phase adds a transaction-preparation and controlled-write layer. It does not
connect staging packages to active bank records and does not perform an import by
default.

## Active-bank allowlist

Only the four corpus targets declared in `bank_architecture.BANK_TARGETS` are
accepted: `laws.json`, `rulings.json`, `consultations.json`, and
`samples_and_circulars.json`. Reference catalogs, indexes, prompts, and quarantine
files are not writable transaction targets.

## Prepare (default / dry-run)

`prepare_transaction(replacements, data_dir=..., transaction_id=..., expected_sha256=...)`

- Requires existing target files and valid current/replacement UTF-8 JSON.
- Optionally checks caller-supplied current SHA-256 values to prevent stale plans.
- Stores byte-exact backups and replacement payloads under
  `ingestion/transactions/<transaction_id>/`.
- Writes a manifest and append-only-style audit event through atomic JSON writes.
- Never changes an active bank file.

## Commit

`commit_transaction(..., human_approval={approved: true, reviewer_id, decided_at}, commit=True)`

Both the explicit flag and human approval metadata are mandatory. Before the first
write, all current target hashes are rechecked and every replacement is parsed.
A process-exclusive lock prevents concurrent writers. Each target is replaced via
same-directory temporary file + `fsync` + `os.replace`. If a later replacement
fails, already replaced targets are restored from exact backups on a best-effort
basis and a failure event is journaled.

This is a recoverable multi-file transaction, not a filesystem-wide atomic
multi-file visibility guarantee: a concurrent reader could observe the brief
interval between per-file replacements. The lock serializes writers, not readers.

## Rollback

`rollback_transaction(..., human_approval=..., rollback=True)` requires separate
explicit approval and checks that each active file still matches the committed
post-write hash before restoring backups. A mismatch blocks rollback rather than
overwriting subsequent edits.

## Safety boundaries

- No automatic legal-effect determination, deduplication, or staging import.
- JSON syntax validation is not a consumer-schema or legal-validity guarantee.
- Production bank writes remain disabled unless a caller deliberately invokes
  commit with both approval and the explicit flag.
- Test coverage uses temporary directories only; no production bank file is used.
