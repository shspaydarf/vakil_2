# MACHINA — Lawyer Memory Stage 5.6: Mini App Management UI

Date: 2026-10-31
Base: Stage 5.5 History & Compare ZIP

## Scope

This stage connects the already implemented and authenticated Stage 5 lifecycle APIs to the existing Mini App lawyer-preference modal. It does not replace the Mini App, change the bot, alter database schema, or modify legal-data assets.

## User-facing controls

- Current memory state and current profile version.
- Activate/deactivate using the existing status endpoints, explicit confirmation, and `expected_profile_version`.
- Bounded history view (up to 50 snapshots), newest first, with date, version, change type, and preference count.
- Restore a selected prior version through the existing restore endpoint. UI explains that restoration creates a new version and preserves previous snapshots.
- Directional comparison of two selected versions, showing added, removed, and changed preference fields with before/after values.
- Permanent delete through the existing DELETE endpoint. The UI requires two browser confirmations and sends `confirm_action: true` plus the current expected version. It explains that only memory/profile history is removed, not cases or documents.
- Refresh and retry states for history retrieval.

## Security and behavior

- No owner/user ID is sent by the browser; the API continues deriving the owner from authenticated Telegram initData.
- Every persistent lifecycle mutation carries the current profile version for optimistic concurrency.
- Persistent mutations require explicit confirmation in the UI and the server-side confirmation flag.
- History and compare are read-only. No snapshot is modified in the browser.
- The manager is hidden when no preference profile exists. Demo mode does not issue persistent requests.
- Existing preference form, suggestion, preview, and save behavior is retained.
- Output values and API error messages are HTML-escaped before rendering.

## Files changed

- `miniapp/app.js`: memory status, history, restore, compare, delete flows and UI rendering.
- `miniapp/styles.css`: responsive MACHINA-styled lifecycle panel, history cards, diff states, and destructive-action zone.
- `tests/test_lawyer_preference_miniapp_stage5_6.py`: integration/source-contract checks.

No backend route or storage changes were needed; Stage 5.5 already exposed the required authenticated endpoints.

## Verification

- `node --check miniapp/app.js`: passed.
- `python -m compileall -q legal_bot`: passed.
- Targeted test selection: **44 passed**.
- API-importing test collection remains blocked by the base ZIP's missing `legal_bot/data/iran/legal_glossary.json`. No fabricated legal glossary was added. The affected API tests were not counted as passing.

## Not included

- Stage 5.7 integrated security/QA.
- Full project regression suite and HTTP end-to-end testing.
- New visual assets or animation; the UI uses existing CSS and restrained styling.
