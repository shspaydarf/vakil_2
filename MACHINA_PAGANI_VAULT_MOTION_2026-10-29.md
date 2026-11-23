# MACHINA — Case Vault Mechanical Motion

## Implemented
- Enhanced the existing decorative case-vault latch: its center mechanism now turns with the handle as the cabinet opens/closes.
- Opening the cabinet gives the visible case cards and the new-case control a brief, staggered tray-slide motion to evoke files moving out of a mechanical cabinet.
- Updated the latch's accessible label to describe its open/close action.
- Motion is decorative only; case data, access control, API, database, routing, and legal logic are unchanged.
- Added `prefers-reduced-motion` handling. No images, fonts, or dependencies added.

## Checks
- `node --check miniapp/app.js`: PASS
- `python -m compileall -q legal_bot`: PASS
- `python preflight.py`: PASS
- `pytest -q`: 105 passed
- Live Telegram/device visual testing: not performed.
