# MACHINA — Lawyer Memory Lifecycle Design
## Stage 5.1 / Design Contract

**Status:** DESIGN COMPLETE — NO RUNTIME CODE CHANGED  
**Base:** `MACHINA_Lawyer_Memory_Stage4_5_Integration_QA_2026-10-31.zip`  
**Scope:** Personal lawyer preference memory only. No case/client memory, no firm sharing, no automatic learning.

## 1. Verified baseline in the supplied Stage 4.5 archive

The following are present in the archive:

- `lawyer_preference_profiles` stores one current profile per `user_id`; its `status` column is constrained to `active` or `inactive`.
- `lawyer_preference_versions` stores append-only snapshots. The database prevents UPDATE of historical rows and allows change types `created`, `updated`, `activated`, `deactivated`, and `restored`.
- `save_profile()` creates/updates a confirmed profile and appends a version in one `BEGIN IMMEDIATE` transaction. It checks `expected_profile_version` and raises on stale versions.
- `get_profile()` reads the current profile; `list_profile_versions()` returns bounded owner-scoped snapshots.
- The authenticated API currently exposes schema/profile loading, `/lawyer-preferences/history`, preview, suggestion and save.
- `load_ai_preference_context()` returns no preference context unless the current profile exists and has status `active`.

**Important correction to earlier planning language:** the database schema anticipates activation/deactivation/restoration change types, but the supplied code does not yet implement lifecycle service methods or activate/deactivate/restore/delete API actions. The history endpoint exists, but it is not a complete management UI.

## 2. Lifecycle state model

| Logical state | Persistence representation | AI behavior | Allowed transitions |
|---|---|---|---|
| `not_created` | No profile row | No preference context | create → `active` |
| `active` | Profile row, `status='active'` | Load confirmed preferences | deactivate → `inactive`; update → `active`; restore → `active` |
| `inactive` | Profile row, `status='inactive'` | No preference context | activate → `active`; edit → remain `inactive`; restore → `active` only after explicit confirmation |
| `deleted` | No profile row and no version rows | No preference context | create anew → `active` |

`deleted` is a logical UI result, not a retained database status or tombstone. A hard delete removes the current profile and every version snapshot. The system must not retain preference content in a deletion tombstone.

## 3. Invariants

1. **Owner isolation:** every read/write/delete is scoped to the UID from the authenticated Telegram dispatcher/session. A request-body `user_id`/`owner_id` is never authoritative.
2. **AI gating:** only a profile in `active` state may be supplied to AI. `inactive`, missing, deleted, malformed, or inaccessible profiles produce an empty preference context.
3. **No case memory:** preference storage accepts only the canonical normalized preference schema. Case documents, client identities, case facts, arbitrary notes and prompt text remain out of scope.
4. **Explicit confirmation:** permanent edits, restore, activation/deactivation where appropriate, and hard deletion require an explicit user action. Preview is non-persistent.
5. **Append-only history:** existing version rows are never updated. Update, status transition and restore append a new version.
6. **Optimistic concurrency:** all mutating actions carry `expected_profile_version`; stale writes return HTTP 409 and never silently overwrite newer data.
7. **Atomicity:** current profile mutation and snapshot insertion occur in one `BEGIN IMMEDIATE` transaction; either both commit or neither does.
8. **Fail-safe AI:** storage/validation errors never inject partial or untrusted preference instructions. The AI call continues without personalized preferences where the current architecture permits.
9. **No raw preference logging:** API/application logs must not contain preference values or full snapshots.
10. **No hidden auto-learning:** AI output or inferred behavior never changes saved preferences without a separate lawyer-confirmed save.

## 4. Versioning and transition semantics

- First confirmed save: version `1`, `change_type='created'`.
- Edit: increment by exactly one, `change_type='updated'`.
- Deactivate: increment by one, preserve preferences and metadata, set status inactive, `change_type='deactivated'`.
- Activate: increment by one, preserve preferences and metadata, set status active, `change_type='activated'`.
- Restore version N: validate that N belongs to the authenticated owner; copy its normalized preferences/metadata into the current profile as a **new** version `current+1`, `change_type='restored'`. Never rewind the counter or mutate the selected historical row.
- Hard delete: in one transaction delete all rows from `lawyer_preference_versions` for the owner and then the `lawyer_preference_profiles` row. The versions table references `users`, not the profile table, so deleting only the profile will NOT cascade-delete its snapshots. This explicit two-table deletion is mandatory.
- Re-create after deletion: starts a new profile at version `1`. No old preference history is recoverable after confirmed hard deletion.

## 5. History retention and presentation

- Keep all versions while the profile exists in the current initial release; do not prune history silently.
- API history reads remain bounded (default 20, hard maximum 50) and newest-first.
- UI should show version number, timestamp, change type and a safe summary of changed preference fields. Avoid exposing internal database IDs.
- A future retention cap may be introduced only with an explicit migration/policy decision and user-facing disclosure. No automatic pruning is included in Stage 5.1.

## 6. Planned service/API contract (design only)

Existing endpoints remain compatible. Proposed additions:

| Method | Route | Purpose | Required safeguards |
|---|---|---|---|
| `POST` | `/api/v1/lawyer-preferences/deactivate` | Disable AI use but retain profile | authenticated UID, expected version, explicit confirmation |
| `POST` | `/api/v1/lawyer-preferences/activate` | Re-enable AI use | authenticated UID, expected version, explicit confirmation |
| `POST` | `/api/v1/lawyer-preferences/restore` | Restore selected version as new current version | owner-scoped target version, expected current version, explicit confirmation |
| `DELETE` | `/api/v1/lawyer-preferences/profile` | Permanently delete profile and all snapshots | expected version, explicit confirmation, atomic two-table delete |
| `GET` | `/api/v1/lawyer-preferences/history` | Existing bounded history | authenticated UID only; preserve existing response shape |

Payload rules:
- Mutations use `expected_profile_version` and `confirm_action: true` (or the existing explicit confirmation field where compatibility requires it).
- Restore additionally uses `source_profile_version`.
- No mutation accepts an owner ID from the client.
- Delete confirmation must be a deliberate second-step action in the UI; do not treat a normal Save click as deletion consent.
- Return only a safe profile DTO (`exists`, `status`, `profile_version`, timestamps and counts); never return `user_id` to browser code.

## 7. Error contract

- Missing profile for activate/deactivate/restore: stable `404 preference_profile_not_found`.
- Stale version: existing `409 preference_version_conflict`.
- Target snapshot not owned by caller / nonexistent: generic `404 preference_version_not_found` (do not disclose another user's data).
- Missing explicit confirmation: `400 confirmation_required`.
- Integrity mismatch between current version and latest snapshot: `409 preference_integrity_conflict`; do not mutate.
- Invalid transition or malformed input: `400 invalid_preference_lifecycle_action`.
- Internal storage failure: generic server error; no raw SQL or preference values in response/logs.

## 8. Implementation sequence after Stage 5.1

- **5.2:** activate/deactivate service and API, transaction + snapshot tests, AI gating tests.
- **5.3:** restore service/API, owner isolation, stale-version and restore-as-new-version tests.
- **5.4:** confirmed hard delete, explicit deletion of snapshots and profile, re-create semantics, privacy tests.
- **5.5:** history summaries and version comparison service; bounded output and no sensitive payload leakage.
- **5.6:** Mini App lifecycle/history UI, preview-before-restore and deliberate delete confirmation.
- **5.7:** end-to-end security, concurrency, regression and Telegram WebView tests.

## 9. Acceptance criteria for Stage 5.1

- The supplied implementation has been inspected rather than assuming planned APIs already exist.
- State transitions, AI behavior, version semantics, delete semantics and error behavior are defined.
- The important non-cascading version-history deletion issue is explicitly documented.
- Existing routes/data contracts are preserved unless a later implementation stage explicitly extends them.
- No runtime behavior or database schema is changed in this design-only stage.

**Stage 5.1 result:** PASS — design contract and machine-readable specification added. Runtime implementation is intentionally deferred to Stage 5.2 onward.
