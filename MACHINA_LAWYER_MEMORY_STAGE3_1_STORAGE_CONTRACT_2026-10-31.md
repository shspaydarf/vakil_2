# MACHINA — Lawyer Memory | Stage 3.1: Persistent Storage Contract

**Date:** 2026-10-31  
**Status:** Design contract only — no application code, database, API, or Mini App changes in this substage.  
**Base:** Batch 21 Stage 5 Final QA.  
**Scope:** Persistent, owner-scoped storage for the existing seven-category lawyer preference form. Digital/AI menu only.

## 1. Objective

Define the exact persistence model before implementation. The existing preference form, schema, normalization, controlled feedback proposals, preview, and authenticated API dispatcher remain the source of truth for field names and allowed values. Stage 3.1 must not recreate those features or alter the Gramophone/classic experience.

The durable profile is a set of explicitly saved working preferences. It is not case memory, client memory, legal knowledge, or a source of legal truth.

## 2. Existing foundations confirmed

- `legal_bot/lawyer_preferences.py` defines the seven categories and allowlisted fields/options, `normalize_preferences()`, and controlled feedback proposals.
- `GET /api/v1/lawyer-preferences/schema`, `POST .../preview`, and `POST .../suggest` already run through the authenticated API dispatcher.
- The dispatcher supplies the authenticated `uid`; request bodies must never choose the owner.
- SQLite access is centralized through `legal_bot.db.conn()` with foreign-key enforcement enabled per connection.
- Startup currently calls `init_db()` and a sequence of idempotent table/upgrade initializers in `legal_bot/main.py`; the API server has its own DB initialization sequence. The future initializer must be added consistently to both startup paths and test fixtures.
- Stage 2 is intentionally stateless. No existing lawyer preference rows need migration or backfill.

## 3. Data model decision

Use two tables in the existing SQLite database:

1. `lawyer_preference_profiles`: one current profile per authenticated user.
2. `lawyer_preference_versions`: immutable snapshots of each successfully saved profile version.

Do not create a separate database, cloud memory service, case-linked table, or organization-sharing model in this project stage.

### 3.1 Current profile table

| Column | Type | Rule / purpose |
|---|---|---|
| `user_id` | INTEGER | Primary key; FK to `users(user_id)` with `ON DELETE CASCADE`. This is the owner; never accepted from client payload. |
| `preferences_json` | TEXT | Canonical normalized JSON object containing only allowlisted category/field values. |
| `field_metadata_json` | TEXT | Per-field provenance and timestamps, keyed by `category.field`. |
| `schema_version` | TEXT | Preference schema version, initially `1.0`. |
| `profile_version` | INTEGER | Positive monotonically increasing version; starts at 1. |
| `status` | TEXT | `active` or `inactive`; only active profiles may be loaded by AI. |
| `created_at` | TEXT | UTC ISO-8601 timestamp. |
| `updated_at` | TEXT | UTC ISO-8601 timestamp of last successful save/status change. |
| `confirmed_at` | TEXT | UTC ISO-8601 timestamp of the lawyer's latest explicit save confirmation. |

Constraints and indexes:
- `PRIMARY KEY(user_id)` guarantees at most one current profile per lawyer.
- `CHECK(profile_version >= 1)`.
- `CHECK(status IN ('active','inactive'))`.
- FK to `users(user_id)` with `ON DELETE CASCADE`.
- No index beyond the primary key is required for the current access pattern.
- JSON is validated in application code using the existing allowlist. Do not depend on SQLite JSON1 being installed for correctness.

### 3.2 Immutable version table

| Column | Type | Rule / purpose |
|---|---|---|
| `id` | INTEGER | Primary key. |
| `user_id` | INTEGER | Owner ID; FK to `users(user_id)` with `ON DELETE CASCADE`. |
| `profile_version` | INTEGER | Version number within this user's profile. |
| `schema_version` | TEXT | Schema version used for the snapshot. |
| `preferences_json` | TEXT | Exact normalized preferences snapshot after the change. |
| `field_metadata_json` | TEXT | Exact provenance snapshot corresponding to the preferences. |
| `change_type` | TEXT | `created`, `updated`, `activated`, `deactivated`, or `restored`. |
| `created_at` | TEXT | UTC ISO-8601 timestamp. |

Constraints and indexes:
- `UNIQUE(user_id, profile_version)`.
- `CHECK(profile_version >= 1)`.
- `CHECK(change_type IN ('created','updated','activated','deactivated','restored'))`.
- FK to `users(user_id)` with `ON DELETE CASCADE`.
- Index `(user_id, profile_version DESC)` for owner-scoped history reads.
- Do not FK the version rows to the current-profile row: deleting a profile must be handled explicitly and atomically, not accidentally leave or cascade unpredictably through a parent-profile relationship.

### 3.3 Atomicity

Every save/status transition must run in one SQLite transaction:
1. Resolve current row using authenticated `user_id`.
2. Check `expected_profile_version` to prevent overwriting a newer edit.
3. Normalize and validate the complete preference object.
4. Write/update the current profile.
5. Insert the matching immutable snapshot.
6. Commit only if both writes succeed.

A failure at any point rolls back both the current profile and history row. Use a write transaction (`BEGIN IMMEDIATE`) for version allocation/update so two concurrent saves cannot receive the same version.

## 4. Canonical JSON shape

`preferences_json` stores only non-empty, explicitly selected values. The seven current category keys remain:

- `professional_context`
- `writing_style`
- `legal_analysis`
- `citations_and_sources`
- `output_formats`
- `document_review`
- `assistant_interaction`

The field names and values must remain exactly those returned by `get_schema()` and accepted by `normalize_preferences()`. Do not duplicate or independently redefine the allowlist in the repository layer.

Rules:
- Omitted category/field means **unset**, not false, not empty, and not a confirmed preference.
- Explicit `false` for a tri-state boolean is retained as a real preference.
- Empty strings and empty categories are removed during normalization.
- Multi-select values are de-duplicated and retain the normalized order from the existing validator.
- Unknown category/field/value is rejected; never silently persisted.
- A profile may be saved with `{}`. This means the lawyer intentionally saved an empty profile, not that the system has inferred preferences.
- Neutral runtime defaults are supplied by consumers only when a preference is unset. They are not written into `preferences_json` as lawyer choices.

Example (illustrative only):

```json
{
  "professional_context": {"practice_areas": ["contracts", "property"], "jurisdiction": "حقوق ایران"},
  "writing_style": {"tone": "formal", "detail_level": "balanced"},
  "legal_analysis": {"counterargument_review": true, "uncertainty_handling": false}
}
```

## 5. Field provenance contract

`field_metadata_json` uses the same `category.field` paths as the preference object. Each currently set field has:

```json
{
  "writing_style.detail_level": {
    "origin": "lawyer_entered",
    "created_at": "2026-10-31T12:00:00Z",
    "updated_at": "2026-10-31T12:00:00Z",
    "confirmed_at": "2026-10-31T12:00:00Z"
  }
}
```

Allowed origins:
- `lawyer_entered`: entered/selected directly by the lawyer.
- `lawyer_confirmed_suggestion`: a controlled proposal explicitly applied and saved by the lawyer.

`system_default` is a runtime fallback origin, not a lawyer preference. It must not be written as a confirmed preference in this profile. If a future UI needs to show defaults, return them separately from persisted preferences.

On an unchanged field, preserve its original `created_at` and origin; update `updated_at`/`confirmed_at` only when the lawyer explicitly re-confirms or changes it according to the final save semantics. On a changed field, set `updated_at` and `confirmed_at` to the save time. Removed fields have no current metadata entry; their former value remains only in the prior immutable snapshot.

A suggestion remains transient until the lawyer applies it to the form and explicitly saves the profile. Merely requesting or viewing a suggestion creates no profile/version row.

## 6. API contract reserved for implementation

All routes remain behind the existing authenticated dispatcher. Owner identity comes exclusively from the authenticated session/Telegram WebApp validation result.

| Method / route | Purpose | Contract |
|---|---|---|
| `GET /api/v1/lawyer-preferences/profile` | Load current profile | Returns `exists`, `persisted`, `status`, `profile_version`, `schema_version`, `preferences`, and safe timestamps. If absent, returns `exists:false` and an empty preferences object. |
| `PUT /api/v1/lawyer-preferences/profile` | Create or replace profile | Requires `confirm_save:true`, `expected_profile_version` (`0` for first create), and the full `preferences` object. Returns the saved profile/version. |
| `POST /api/v1/lawyer-preferences/profile/deactivate` | Deactivate | Requires `expected_profile_version`; retains data/history but prevents AI consumers from loading the profile. |
| `POST /api/v1/lawyer-preferences/profile/activate` | Reactivate | Requires `expected_profile_version`; only the owner can reactivate. |
| `GET /api/v1/lawyer-preferences/profile/versions` | Read version history | Owner-scoped, bounded pagination; returns version metadata and optionally snapshots only to that same owner. |
| `DELETE /api/v1/lawyer-preferences/profile` | Delete profile | Requires an explicit confirmation flag and expected version. Atomically deletes current profile and all preference snapshots for that user. This is a hard delete; no recovery copy is retained. |

The existing schema/preview/suggest routes remain backward compatible. `preview` continues to mean preview only and must never write data. `suggest` remains proposal-only. `GET profile` should not create an empty row as a side effect.

### Save conflict behavior
- First save: `expected_profile_version = 0` and no current row.
- Update: expected version must equal the current version.
- Mismatch: return HTTP `409` with a stable `profile_version_conflict` code and the current version; do not overwrite.
- A retry must reload and reconcile the latest profile; never silently last-write-wins.

### Response privacy
- Return only preference values, provenance, version/status and timestamps needed by the owner UI.
- Never return another user's existence, profile, or version history.
- Never include client/case information, raw AI prompts, generated documents, or hidden system configuration.

## 7. Privacy and input validation

The profile accepts general working preferences only. It must never accept case-specific memory, client identity, documents, privileged communications, or legal facts.

Validation layers for implementation:
1. Reuse `normalize_preferences()` as the canonical allowlist and type/length validator.
2. Enforce strict request-size and field-length limits before parsing/processing.
3. Reject obvious high-risk identifiers in free-text fields where reliably detectable (for example Iranian mobile numbers, ten-digit national-ID-shaped values, email addresses, and long case/reference-number patterns). Return a field-level validation error; do not silently redact and save a modified value.
4. Detection is heuristic and cannot guarantee semantic detection of names or confidential facts. Keep the UI warning and state this limitation; do not claim automated confidentiality screening is complete.
5. Do not log raw preference text or request bodies. Logs may contain user ID, action, result code, profile version, and timestamp only.
6. Parameterize all SQL. Never interpolate owner IDs or user-supplied values into SQL strings.
7. Every read/update/delete query includes authenticated `user_id`; never look up a profile by a client-supplied ID alone.

## 8. Deactivation, deletion, and retention semantics

- `inactive`: retain the current profile and versions for the lawyer to reactivate; all AI preference loaders must treat it as absent.
- `DELETE`: hard-delete current row and all version snapshots in one transaction. No soft-delete tombstone containing preference data.
- User-account deletion: FK cascade removes current profile and history.
- No automatic expiry or background learning in this stage.
- Do not export or share profiles to firm admins or other lawyers. Organization-level sharing is out of scope and defaults to disabled.

## 9. Migration and compatibility plan

- No existing profile data is migrated because Stage 2 did not persist any.
- Add an idempotent initializer in `legal_bot/db.py` (proposed name: `init_lawyer_preference_tables()`), following the project's existing initializer pattern.
- Add it to both application startup paths (`legal_bot/main.py` and API server initialization) and relevant test fixtures in the implementation substage.
- Do not alter existing `users`, case, client, case-document, AI-history, or Gramophone tables.
- Do not change existing preference field keys or option values without a separate schema-versioned compatibility decision.
- Future schema upgrades must preserve old snapshots as historical data; current profile migration should be explicit and tested.

## 10. Acceptance criteria for Stage 3.1

- The two-table model and all columns/constraints are documented.
- The canonical JSON shape matches the existing seven-category schema.
- Unset values, explicit false, provenance, and system defaults are unambiguous.
- Save/version writes are atomic and optimistic-concurrency protected.
- Read/write/deactivate/delete semantics are defined.
- Owner identity and privacy boundaries are explicit.
- Migration entry points are identified.
- No code, database, API, UI, or existing behavior has changed in this substage.

## 11. Next substage

**Stage 3.2 — Persistence engine:** implement the idempotent tables, repository operations, transaction/version handling, and focused database tests. API wiring and Mini App integration remain later subtasks; do not bundle them into 3.2.
