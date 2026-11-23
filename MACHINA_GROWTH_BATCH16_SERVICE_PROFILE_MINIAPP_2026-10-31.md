# MACHINA Growth Batch 16 — Lawyer Service Profile in Mini App

Date: 2026-10-31

## Scope
Connected the existing Telegram lawyer service-listing workflow to the Mini App. This is an integration-only batch; no competitor-driven quality upgrades or broad refactors were included.

## Mini App
- Added **پروفایل خدمات من** to the existing classic tools hub.
- Supports listing the signed-in user's own profiles, creating, editing, and soft-deleting them.
- Form fields match the existing bot service listing schema: name, phone, city, specialty, service title, fee type/value, description, and charitable flag.
- New and edited submissions require a JPG/PNG/WEBP lawyer-license image (max 6 MB).
- Shows review status; the lawyer cannot approve their own listing.

## API and workflow
- `GET /api/v1/services`
- `POST /api/v1/services` (multipart form + license photo)
- `PATCH /api/v1/services/{id}` (multipart form + fresh license photo)
- `DELETE /api/v1/services/{id}` (soft delete)
- Read/edit/delete are scoped to the authenticated Telegram user. A foreign user's listing returns not-found on edit/delete and is never included in their listing.
- Reuses the existing `service_listings` database functions and existing admin callback payloads `serviceadmin:approve:{id}` / `serviceadmin:reject:{id}`.
- License image is forwarded to the configured admin Telegram account(s) for manual review. The API does not store the image or its Telegram file_id in the service listing table.
- Editing returns the listing to `pending`, so it requires review again. Admin approval/rejection remains in the existing Telegram admin workflow.

## Verification
- Full test suite: **288 passed**.
- Added two tests for ownership/soft-delete behavior and form validation.
- `node --check miniapp/app.js`: PASS.
- `python -m compileall -q legal_bot`: PASS.
- `python preflight.py`: PASS.

## Not live-tested
The automated tests do not perform a real Telegram license-photo upload or deliver actual admin notifications. Those calls require the deployed bot token and configured admin IDs. No live Telegram WebView test or load test was performed. Manual admin review remains required; submitting a profile does not make it publicly active.
