# MACHINA — Lawyer Memory Stage 5.4: Hard Delete

Date: 2026-10-31
Base: Stage 5.3 Restore ZIP

## Scope delivered

- Added `hard_delete_profile()` to the preference store.
- Added the service adapter `delete_editor_profile()`.
- Added authenticated `DELETE /api/v1/lawyer-preferences/profile` API route.
- The authenticated UID is the only owner key; payload owner fields are ignored.
- The request requires `confirm_action: true` and `expected_profile_version`.
- Uses `BEGIN IMMEDIATE`, checks the current profile version, and verifies the full history is contiguous by count and maximum version before deletion.
- Explicitly deletes all `lawyer_preference_versions` rows and then the profile row in the same transaction. This is necessary because version rows reference `users`, not the profile table.
- Any failure rolls back both deletions. No tombstone or retained history is written.
- Re-creating a profile after deletion starts at version 1.

## Safety semantics

- Missing profile: 404 `preference_profile_not_found`.
- Missing confirmation: 400 `confirmation_required`.
- Stale profile version: 409 `preference_version_conflict`.
- History mismatch: 409 `preference_integrity_conflict`; deletion is refused.
- The operation affects only the authenticated owner's preference profile/history. It does not delete cases, documents, clients, or account data.

## Validation

Passed 49 targeted tests across Stage 5.4 deletion, Stage 5.2 lifecycle, Stage 5.3 restore, and AI preference context/integration tests. Python syntax compilation passed for the modified store, service, and API modules.

This is targeted validation, not a claim that the entire application test suite passes. The known missing `legal_glossary.json` in the supplied base package remains untouched; no synthetic legal data was added.

## API example

`DELETE /api/v1/lawyer-preferences/profile`

```json
{
  "expected_profile_version": 4,
  "confirm_action": true
}
```

A successful response returns `deleted: true` and `deleted_versions`.

## Not included

- History comparison UI/API enhancements (Stage 5.5)
- Mini App lifecycle management UI (Stage 5.6)
- Final integrated security/QA pass (Stage 5.7)
