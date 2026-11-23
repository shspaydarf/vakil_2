# MACHINA Audit — Stage 2: Lawyer Memory & Preferences
Date: 2026-10-30

## Scope
Reviewed the existing lawyer preference capture feature from the full project ZIP. This audit covers the Mini App entry point, UI form, schema endpoint, feedback suggestion endpoint, preview endpoint, validation, authentication routing, and the boundary between temporary preferences and future persistent memory.

## Confirmed behavior
- The settings entry is present in the account modal and opens the preference form inside the Mini App.
- The form contains seven categories: professional context, writing style, legal analysis, citations and sources, output formats, document review, and assistant interaction.
- All fields are optional. Unset values are omitted and are not silently converted into defaults.
- Server-side validation allowlists categories, fields, select options, multi-select values, boolean values, and text lengths.
- Feedback signals are controlled and deterministic. They create proposals only; the user must explicitly add a proposal to the form.
- The API routes are behind the existing authenticated API dispatcher. The authenticated user ID is not accepted from the request body for this stateless feature.
- The preview endpoint returns normalized values and explicitly reports `persisted: false`.
- The feature does not read case documents, client data, or case history to infer preferences.
- The UI uses the existing MACHINA modal, card, form, and button styling.

## Issue found and fixed in this audit
The original multi-select fields used native HTML `<select multiple>`. On many mobile WebViews this is difficult to discover and operate, and does not provide a consistent touch-friendly selection experience. Replaced it with styled checkbox groups that:
- are easier to tap on mobile;
- preserve multi-select behavior;
- are collected into the same API payload shape;
- remain compatible with suggestion application and server validation.

Also verified and retained suggestion application for both checkbox groups and scalar select/text fields.

## Important scope boundary — not a defect in this stage
This is **not yet a persistent memory system**. It is Stage 2 preference capture and preview only.
- No profile is written to SQLite or another database.
- Preferences are not loaded on later sessions.
- Preferences are not yet injected into AI prompts or drafting/review behavior.
- There is no edit/deactivate/delete/history/export interface because no durable profile exists yet.

These are intentionally deferred to the later memory implementation stages. The UI clearly tells the lawyer that preview confirmation is temporary and permanent storage is not enabled yet.

## Privacy and safety observations
- The profile schema is limited to general working preferences and generic professional context.
- The UI warns against entering client names, case numbers, case facts, documents, or confidential communications.
- The free-text notes are length-limited but are not semantically screened for personal or case data. Since this stage does not persist them, exposure is limited to the request/preview path; Stage 3 should retain the warning and consider stronger input guidance or detection.
- Preferences must never override source verification, legal review, access control, or the lawyer's explicit decision.
- Suggestions must remain proposals until the lawyer applies them; durable persistence will require a separate explicit save confirmation.

## Validation performed
- Full test suite: **204 passed**.
- `node --check miniapp/app.js`: PASS.
- `python -m compileall -q legal_bot`: PASS.
- `python preflight.py`: PASS.
- ZIP integrity check: PASS.

## Not verified
- Live Telegram WebView rendering on physical Android/iOS devices.
- Production authentication against a deployed Telegram Mini App.
- Multi-user load or production database behavior (not relevant to persistence in this stateless stage).
- Whether downstream AI features consume preferences; they intentionally do not yet.

## Conclusion
The Stage 2 preference capture feature is correctly connected to the Mini App and authenticated API, validation and confirmation boundaries are sound for its current stateless scope, and the mobile multi-select UX has been improved. Do not describe this as persistent lawyer memory until Stage 3 storage and Stage 4 AI integration are implemented and tested.
