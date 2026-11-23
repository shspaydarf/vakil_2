# MACHINA AI Stage 5 — Workflow Handoff and Contract Review Integration

## Scope
This change is confined to the digital AI menu workflow in `legal_bot/handlers.py` and callback registration in `legal_bot/main.py`, with focused tests. The Gramophone/traditional area, unrelated app menus, Mini App UI, database schema, and legal JSON files were not intentionally changed.

## Implemented
- Added a follow-up action for specialized contract review after the existing case issue/contradiction review flow.
- Added an explicit `aicontract:<case_id>` callback, registered in the Telegram callback router.
- The handler verifies lawyer access, parses the case identifier, confirms the case belongs to the current Telegram user and is not archived, and reads only that user's extracted case text.
- Contract review is blocked unless AI processing and external-data consent are enabled.
- Reserves an AI entitlement before the request, commits it on success, and refunds it on failure.
- Calls the existing `review_contract_risks` helper; does not send original files, PDFs, or images to the external model.
- Displays a review disclaimer and preserves a route back to the selected case and AI menu.

## Not claimed
- This is not an autonomous end-to-end legal workflow; the user explicitly chooses the contract-review handoff.
- Contract type is currently passed as `نامشخص`; automatic contract classification is not implemented here.
- No real external-model run, live Telegram interaction, or legal-quality benchmark was performed.
- The extracted-text completeness limitations of earlier stages remain.

## Validation
- `pytest -q`: 133 passed.
- `python -m compileall -q legal_bot`: passed.
- `node --check miniapp/app.js`: passed.

## Changed files
- `legal_bot/handlers.py`
- `legal_bot/main.py`
- `tests/test_ai_stage5_workflow_handoff.py`
- This report
