# MACHINA Growth Batch 3 — Saved Documents

Date: 2026-10-30
Base: Growth Batch 2 — Recent Activity

## Delivered
- Added a per-lawyer `lawyer_saved_documents` table with a composite key on `(user_id, case_id, document_id)`.
- Added database operations to save/unsave a document and list saved document metadata.
- Ownership is verified against both the authenticated lawyer and the case/document relationship before saving.
- Added authenticated API endpoint `GET /api/v1/saved-documents?limit=...`.
- Added authenticated `PATCH /api/v1/cases/{case_id}/documents/{document_id}/pin` with strict boolean validation.
- The case documents response now includes a `saved` flag for each document.
- Added a Mini App home shelf, “اسناد نشان‌شده”, and star controls in the document list.
- Tapping a saved item reopens its case and document list; no document text is duplicated into the saved-items table or endpoint.
- Added responsive styling consistent with the existing MACHINA paper/metal palette.

## Scope boundary
This batch saves uploaded case documents only. AI answers and generated drafts are not included because the current AI answer surface is not itself a stable saved artifact in this workflow. Draft artifact bookmarking should be implemented only against its durable artifact ID and ownership model in a later, separate change. No claim is made that transient AI output is persisted.

## Validation
- Full test suite: 214 passed.
- `node --check miniapp/app.js`: passed.
- `python -m compileall -q legal_bot`: passed.
- `python preflight.py`: PASS.
- ZIP integrity: checked after packaging.

## Not yet performed
- Live Telegram Mini App verification.
- Production database migration against a copy of the deployed database.
- Multi-user load testing.
