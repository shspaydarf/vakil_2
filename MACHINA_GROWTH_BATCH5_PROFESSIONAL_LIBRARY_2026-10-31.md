# MACHINA Growth Batch 5 — Professional Work Library

Date: 2026-10-31
Base: `LegalBot_MACHINA_Calendar_Weekly_Time_Upgrade_2026-10-31.zip`

## Purpose
Extend the existing Mini App work-product/history shelf into a reusable personal work library, without adding a new top-level menu or duplicating the existing case/AI/Playbook systems.

## Delivered
- Added a second tab inside the existing "کتابخانه کار و خروجی‌ها" shelf: "دستورها و قالب‌های من".
- Added seven curated starter resources (five reusable prompts and two drafting/document-structure templates).
- Added private, per-authenticated-lawyer storage for personal prompts and templates.
- Added create, edit, delete, search, and type filtering (prompt/template).
- Added "ذخیره دستور" in the existing case AI composer to save a prompt directly into the library.
- Added "استفاده در پرونده"; selecting a resource opens the existing case picker and pre-fills the existing AI question box. It does not submit or spend AI quota automatically.
- Kept existing work-product history, search and bookmarks in the first tab.
- Added API routes under authenticated `/api/v1/lawyer-library`; ownership is derived from the authenticated user, never from request body.
- Added server-side validation: title <= 100 chars, category <= 60, description <= 240, content <= 6,000, maximum 100 personal resources per lawyer.
- Personal resources are not shared across lawyers. Starter resources are static examples and are not legal authorities.

## Deliberately not included
- Existing contract Playbooks remain in their current Telegram-bot flow; this batch does not falsely expose them as Mini App workflows.
- No automatic AI execution when a prompt is selected.
- No client/case-specific confidential facts are inferred into reusable resources.
- No firm/team sharing or global admin publishing.

## Verification
- Full automated test suite: 232 passed.
- `node --check miniapp/app.js`: passed.
- `python -m compileall -q legal_bot`: passed.
- `python preflight.py`: passed.
- ZIP integrity: checked after packaging.

## Remaining real-world checks
- Open Mini App inside Telegram and verify the tab, modal, save/edit/delete and prompt-apply flows on Android/iOS.
- Verify authenticated API calls against the deployed environment.
- No live Telegram or concurrent-user load test is claimed by this report.
