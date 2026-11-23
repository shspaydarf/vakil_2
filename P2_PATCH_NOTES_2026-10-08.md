# P2 maintenance patch — 2026-10-08

## Changes
- Renamed the user-facing case file callback namespace from the misleading `cplaceholder:*` to `cfile:*`.
- Kept `cplaceholder:*` as a backward-compatible callback pattern so old Telegram messages/buttons do not break.
- No database schema or case/document business logic was changed.
- Existing `placeholder` terminology inside drafting/review engines was intentionally retained because those are real audit placeholders, not dead code.

## Validation
- Python syntax check
- JavaScript syntax check
- Full pytest suite
- Legacy callback compatibility check
