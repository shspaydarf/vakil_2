# MACHINA — Lawyer Preference Memory — Stage 5.2

Date: 2026-10-31
Base: Stage 5.1 Lifecycle Design ZIP
Scope: Activate / deactivate lifecycle operations only.

## Implemented

- Added transactional `set_profile_status()` in `legal_bot/lawyer_preference_store.py`.
- Added service wrapper `change_editor_status()`; authenticated UID is passed separately and any owner identifier in the payload is ignored.
- Added POST routes:
  - `/api/v1/lawyer-preferences/deactivate`
  - `/api/v1/lawyer-preferences/activate`
- Both operations require `confirm_action: true` and `expected_profile_version`.
- Uses `BEGIN IMMEDIATE`, owner scoping, optimistic version matching, and verifies the latest immutable snapshot before mutation.
- Status change increments the profile version and appends a snapshot with `deactivated` or `activated` change type in the same transaction.
- Existing preference values and field metadata are preserved.
- Repeating the already-current status is idempotent and does not create a redundant version.
- Missing profiles map to HTTP 404 (`preference_profile_not_found`); stale versions map to existing HTTP 409 handling; missing confirmation maps to HTTP 400.
- AI context remains empty while inactive and resumes from the preserved preferences after activation.

## Tests

Passed: 50 targeted tests across lifecycle store, preference store/service, and AI preference-context/conflict/integration modules.

The API test module could not be collected in this source ZIP because the existing repository is missing `legal_bot/data/iran/legal_glossary.json`; importing `legal_bot.api` loads `legal_bot.glossary` and fails before tests execute. No substitute legal glossary was fabricated. API source was syntax-compiled separately.

## Not included (by design)

- Restore previous version (Stage 5.3)
- Hard delete (Stage 5.4)
- History compare enhancements (Stage 5.5)
- Mini App controls/UI (Stage 5.6)
- Full integrated QA/security pass (Stage 5.7)

## API request body

```json
{
  "expected_profile_version": 3,
  "confirm_action": true
}
```

No `owner_id` is required or trusted. Owner identity comes from the authenticated request dispatcher.
