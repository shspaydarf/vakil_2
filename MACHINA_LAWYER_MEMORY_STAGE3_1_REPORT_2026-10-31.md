# MACHINA Lawyer Memory — Stage 3.1 Completion Report

**Result:** Complete — storage contract designed and validated.  
**Change level:** Documentation only. No Python/JavaScript source, database, API route, or Mini App behavior was modified.

## Delivered

- `MACHINA_LAWYER_MEMORY_STAGE3_1_STORAGE_CONTRACT_2026-10-31.md`
- `MACHINA_LAWYER_MEMORY_STAGE3_1_STORAGE_CONTRACT_2026-10-31.json`

## Key decisions

- Two SQLite tables: one current owner-scoped profile and immutable per-profile version snapshots.
- One profile per authenticated `user_id`; owner ID is always supplied by the authenticated dispatcher, never by request payload.
- Existing `get_schema()` and `normalize_preferences()` remain the single source of truth for the seven categories and allowed values.
- Unset values remain unset; explicit `false` is preserved; system defaults remain runtime fallbacks, not lawyer-confirmed preferences.
- Per-field provenance distinguishes lawyer-entered preferences from lawyer-confirmed suggestions.
- Atomic writes use `BEGIN IMMEDIATE` and optimistic concurrency (`expected_profile_version`); stale writes return HTTP 409.
- Deactivation retains data but prevents AI consumers from loading it. Explicit deletion hard-deletes the current profile and all snapshots in one transaction.
- Case/client facts, documents, privileged communications, and firm-wide sharing are out of scope.
- No existing profile data requires backfill because Stage 2 was stateless.

## Validation

- Contract JSON parse: PASS.
- Exact category/field parity against live `get_schema()`: PASS.
- Focused preference tests: **12 passed**.
- Full test suite: **323 passed**.
- `node --check miniapp/app.js`: PASS.
- `python -m compileall -q legal_bot tests`: PASS.
- `python preflight.py`: PASS.

## Not claimed / not performed

- No DB migration or persistence code was implemented in Stage 3.1.
- No production database or live Telegram WebView test was performed.
- Heuristic detection of obvious identifiers in free-text fields cannot guarantee detection of all confidential information.

## Next

Stage 3.2 implements only the persistence engine: idempotent table initialization, owner-scoped repository operations, atomic version snapshots, optimistic concurrency, and focused database tests. API/UI wiring remains separate.
