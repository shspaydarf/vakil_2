# MACHINA Growth Batch 2 — Recent Activity

Date: 2026-10-30
Base: `LegalBot_MACHINA_Growth_Batch1_Pinned_Cases_2026-10-30.zip`

## Delivered

- Added a persistent, user-scoped recent-activity table: `lawyer_recent_activity`.
- Added authenticated API endpoints:
  - `GET /api/v1/recent-activity?limit=8`
  - `POST /api/v1/recent-activity` with only `case_id` and an allowlisted `activity_type`.
- Activity types recorded: opening a case, opening case documents, opening drafts, opening the timeline, opening the case AI view, successfully asking AI, and successfully creating a draft.
- Added the Mini App home panel “ادامه از آخرین فعالیت” with direct continuation into the relevant case area.
- Recent activity is scoped to the authenticated lawyer, joined back to cases owned by that lawyer, and archived cases are excluded.
- Only a small activity marker, case ID, activity type, and timestamp are stored. No client names, document contents, AI prompts, or AI answers are copied into this activity table.
- The history is bounded to 60 rows per lawyer; API reads are capped at 20 and Mini App displays 8.
- Added mobile-friendly styling using the existing MACHINA palette.
- Removed a duplicated `pinnedCasesBtn` element ID found in the incoming Batch 1 Mini App HTML.

## Validation

- Full pytest suite: **211 passed**.
- `node --check miniapp/app.js`: passed.
- `python -m compileall -q legal_bot`: passed.
- `python preflight.py`: passed.
- ZIP integrity check: performed after packaging.

## Boundaries / not claimed

- This feature records navigation and selected successful actions going forward; it does not reconstruct historical activity from before this update.
- The panel is implemented in the Mini App. No new Telegram bot menu was added.
- No live Telegram session, external AI provider, production database, or concurrent 200–300 user load test was performed in this package.
