# Stage 5.3 Changelog

- Added `ProfileVersionNotFound` storage exception.
- Added atomic, owner-scoped historical snapshot restore.
- Added service adapter using authenticated UID.
- Registered `POST /api/v1/lawyer-preferences/restore`.
- Added HTTP 404 mapping `preference_version_not_found`.
- Added tests for monotonic versioning, immutable history, inactive-state retention, AI context gating, confirmation, stale versions, cross-owner isolation, invalid/missing versions, rollback, service owner handling and route registration.
