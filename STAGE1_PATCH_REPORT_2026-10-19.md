# LegalBot — Stage 1 Patch Report

Date: 2026-10-19
Base package: `LegalBot_کیلین_P2_fixed_2026-10-08-1.zip`

## Changes applied

1. **Bounded aggregate multipart uploads**
   - Added `MAX_UPLOAD_REQUEST_MB` (default 25 MB, configurable up to 64 MB).
   - The API rejects requests above this aggregate limit before buffering the multipart body.
   - Nginx body limit is set to 26 MB to provide small multipart/proxy overhead above the default API cap.
   - Added the setting to `.env.production.example`.

2. **WebP upload validation consistency**
   - `.webp` was accepted by the API upload allow-list but rejected by the storage content validator.
   - Added RIFF/WEBP signature validation so genuine WebP files can pass the same ingestion validation path and spoofed extensions are rejected.

3. **Archived lawyer-note protection**
   - Clearing a note now follows the same archived-case read-only rule as saving a note.
   - API note clearing verifies case ownership/existence and rejects archived cases.
   - Clearing an already-empty note through the API is now idempotent rather than returning a misleading failure.

4. **Task route/case consistency**
   - Task update/delete routes now verify that the task belongs to the case ID in the URL, not merely that the task belongs to the authenticated user.
   - Existing Telegram callers remain compatible because the database helpers keep `case_id` optional.

5. **Regression tests**
   - Added tests for WebP signature validation, archived note protection, mismatched task/case IDs, and upload/proxy size-limit alignment.

## Validation performed

- `pytest -q`: **56 passed**
- `python preflight.py`: **PASS**
- `python -m compileall -q legal_bot`: **PASS**
- `node --check miniapp/app.js`: **PASS**

## Not verified in this patch

- No real Telegram deployment or end-to-end test was run.
- No external AI provider request was made.
- Docker images/compose were not started against a production host.
- Backup restore, scheduled backup execution, TLS/domain setup, and operational alerting still require host-level verification.
- The API still uses in-memory rate limiting; this is not shared across multiple API processes.

## Important upload behavior

The API enforces an aggregate request cap, not just a per-file cap. With the default configuration, a single file may be up to the configured per-file limit, but the combined multipart request must remain within 25 MB. For a different aggregate cap, set `MAX_UPLOAD_REQUEST_MB` and keep `nginx.conf`'s `client_max_body_size` slightly higher.
