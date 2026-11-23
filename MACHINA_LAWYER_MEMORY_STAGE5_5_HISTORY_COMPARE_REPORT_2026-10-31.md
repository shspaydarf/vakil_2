# MACHINA — Lawyer Memory Stage 5.5: History & Version Comparison

Date: 2026-10-31  
Base: Stage 5.4 Hard Delete ZIP

## Scope delivered

- Kept the existing owner-scoped, bounded history endpoint and preserved its snapshot fields for compatibility.
- Added optional `limit` handling to `GET /api/v1/lawyer-preferences/history`, bounded to 1–50, newest first.
- Added lightweight `count`, effective `limit`, and per-snapshot `selected_count` metadata for a future Mini App history list.
- Added read-only `compare_profile_versions()` in the storage layer.
- Added the authenticated service adapter `compare_history()`; the authenticated UID is authoritative and client-supplied owner IDs are ignored.
- Added `GET /api/v1/lawyer-preferences/compare?from_version=N&to_version=M`.
- Comparison returns deterministic field-level `added`, `removed`, and `changed` entries, with before/after values, timestamps, change types, and schema-change indicator.
- Comparison is directional: reversing the selected versions reverses before/after semantics.
- Both snapshots are selected by `(authenticated user_id, profile_version)`; another owner's version cannot be queried or inferred.
- No history snapshot is changed, pruned, or deleted by listing/comparison.

## Safety and behavior

- Versions must be positive integers; booleans and malformed values are rejected.
- Comparing a version to itself is rejected.
- If either selected version does not belong to the authenticated owner, the service returns the existing `ProfileVersionNotFound` path (HTTP 404), without disclosing whether another owner's version exists.
- The endpoint is read-only and does not require a mutation confirmation.
- Existing history response shape is retained, with additive metadata only.

## API examples

`GET /api/v1/lawyer-preferences/history?limit=20`

`GET /api/v1/lawyer-preferences/compare?from_version=2&to_version=5`

## Validation

- 65 targeted tests passed across the new Stage 5.5 tests, store/service, lifecycle, restore, hard-delete, and AI preference-context suites.
- `py_compile` passed for the modified store, service, and API modules.
- The new tests cover directional diffs, added/removed/changed fields, owner isolation, malformed/same versions, authenticated UID authority, bounded history, and route registration.

This is targeted validation, not a claim that the entire application test suite passes. The known missing `legal_glossary.json` in the supplied base package remains untouched; no synthetic legal data was added.

## Not included

- Mini App history/compare management UI (Stage 5.6)
- Final integrated security and QA pass (Stage 5.7)
