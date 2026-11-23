# Phase 7.9 — Controlled operations and release-readiness

## Scope

Phase 7.9 closes the Phase 7 bulk-ingestion architecture with a bounded pilot
planner, operational dashboard, resumability checkpoint, and fail-closed release
readiness assessment. It does **not** execute acquisition, OCR, import, a
Phase 5.7 transaction, or production activation.

## Operational flow

1. Build a deterministic rollout plan from catalog candidates using the Phase
   7.1 `BatchPolicy` limits. Defaults remain conservative and only
   `official_primary` sources are admitted by default.
2. Keep the plan immutable. Operational progress is supplied as a separate
   append/event stream and summarized by `build_operations_dashboard`.
3. On interruption, write a checkpoint bound to the exact rollout plan hash.
   Recovery must replay/reconcile the event log from the last stable event;
   automatic retries are deliberately not initiated by this module.
4. Use `assess_activation_readiness` to record whether release prerequisites
   have been evidenced. Missing, false, or non-boolean checks fail closed.
5. Even when all readiness checks are true, this result is not an activation
   command. A separate authorized release action and explicit human decision
   remain mandatory.

## Required release evidence

- Source registry reviewed.
- Official-source evidence verified.
- At least one real official PDF sample validated.
- Human review completed.
- Human-labelled golden search queries supplied.
- Search metrics reviewed and accepted.
- Backup/restore drill passed.
- Rollback drill passed.
- Security review passed.
- Operator/reviewer separation confirmed.
- Explicit release approval recorded.

Synthetic fixtures and passing unit tests do not satisfy real-PDF, official
source, legal authenticity, legal force, or production-readiness evidence.

## Safety invariants

- No network access or downloads.
- No automatic retry or CAPTCHA/403/429 bypass.
- No write to active JSON banks or production search index.
- No automatic activation or transaction commit.
- No inference of legal validity, current force, amendment, or repeal.
- Secondary and unverified sources remain excluded by default.
- Every rollout plan and recovery checkpoint is integrity-bound with SHA-256.

## API

- `create_rollout_plan(...)`
- `validate_rollout_plan(plan)`
- `build_operations_dashboard(plan, observed_events=...)`
- `create_recovery_checkpoint(plan, ...)`
- `validate_recovery_checkpoint(plan, checkpoint)`
- `assess_activation_readiness(evidence)`
- `write_json_atomic(payload, destination)`

## Test boundary

Tests use synthetic candidates and event records. They establish deterministic
planning, budget enforcement, plan/checkpoint integrity, fail-closed readiness,
and atomic artifact writing. They do not establish live source reachability or
legal correctness of any document.
