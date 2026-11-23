# MACHINA Lawyer Memory — Stage 3.2 Storage Engine

Date: 2026-10-31

## Scope delivered
- Added `legal_bot/lawyer_preference_store.py` as a separate persistence repository.
- Added additive SQLite tables `lawyer_preference_profiles` and `lawyer_preference_versions`.
- Implemented owner-scoped profile read, confirmed full-profile save, immutable version snapshots, bounded history retrieval, and optimistic concurrency.
- Profile and history writes run in one `BEGIN IMMEDIATE` transaction; a failed snapshot insert rolls back the profile write.
- Preserves explicit `false`, valid empty profiles, canonical preference normalization, per-field origin/timestamps, and confirmed-suggestion provenance.
- Enforces foreign keys to the existing `users` table and does not alter existing tables.

## Deliberately not wired yet
- No API routes or Mini App save/load behavior were changed.
- No startup initializer was added to bot/API entrypoints; that is deferred until the integration/security sub-stages.
- No AI feature consumes persisted preferences yet.
- Activation/deactivation and hard deletion are deferred to later lifecycle/API work.
- Identifier-pattern and sensitive-text screening is reserved for Stage 3.3; the repository schema itself does not accept case/client fields.

## Validation
- Dedicated storage tests cover additive schema, foreign key, save/load, empty profile, explicit false, version conflict, snapshot history, owner isolation, explicit confirmation, metadata origin restrictions, atomic rollback, invalid owner, and bounded history.
- Full project test suite, JS syntax, Python compile, and preflight results are recorded in the delivery message after execution.
