# MACHINA — Lawyer Memory Lifecycle Stage 5.3
## Historical Version Restore

**Status:** Implemented; targeted regression checks passed.

### Scope delivered
- Added owner-scoped `restore_profile_version()` storage operation.
- Added transport-neutral `restore_editor_version()` service operation.
- Added authenticated `POST /api/v1/lawyer-preferences/restore` API route.
- Added stable `404 preference_version_not_found` mapping for a source version that does not exist for the authenticated owner.
- Added explicit confirmation and optimistic concurrency checks.

### Restore semantics
1. The request identifies `source_profile_version` and the current `expected_profile_version`.
2. The authenticated dispatcher UID is the only owner identity used; any owner field in the body is ignored.
3. The source snapshot must belong to that owner.
4. The current profile and latest history version must agree before mutation.
5. A restore creates `current_version + 1` with `change_type=restored`.
6. Historical rows are not updated or deleted.
7. Preferences, field metadata and schema version are copied from the source snapshot.
8. The current active/inactive status is retained. Restoring preferences does not silently reactivate memory.
9. Profile update and new history insert happen in one `BEGIN IMMEDIATE` transaction; snapshot failure rolls back the profile update.
10. AI context remains unavailable for an inactive profile and is available only for an active profile.

### API request contract
`POST /api/v1/lawyer-preferences/restore`

```json
{
  "source_profile_version": 2,
  "expected_profile_version": 5,
  "confirm_action": true
}
```

The `owner_id` is deliberately not accepted as an authority source. The API uses the authenticated Telegram UID.

### Files changed
- `legal_bot/lawyer_preference_store.py`
- `legal_bot/lawyer_preference_service.py`
- `legal_bot/api.py`
- `tests/test_lawyer_preference_restore_stage5_3.py`

### Validation
- Python compilation: passed for all three changed runtime modules.
- Targeted tests: **59 passed** across Stage 5.3 restore, Stage 5.2 lifecycle, AI preference context/integration, store and service tests.
- API module import/HTTP integration tests remain blocked in this ZIP because the baseline does not include `legal_bot/data/iran/legal_glossary.json`; no synthetic legal glossary was created. Route registration and error contract are covered by source-level tests.

### Not included (reserved for later stages)
- Hard deletion (Stage 5.4).
- Version comparison and enhanced history presentation (Stage 5.5).
- Mini App management UI (Stage 5.6).
- Full integrated/security QA (Stage 5.7).
