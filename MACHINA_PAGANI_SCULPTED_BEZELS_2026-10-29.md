# MACHINA — Pagani Sculpted Bezels

## Change
- Enhanced the circular tool-symbol buttons with deeper layered metallic rims, brushed sage/silver gradients, a fine copper inner ring, and stronger physical depth.
- Added a short pressed-in state when a tool tile is activated/focused, while keeping the existing shift-lever interaction and tool routing intact.
- Kept the effect CSS-only: no images, fonts, dependencies, API/database/legal-logic changes.
- Respects `prefers-reduced-motion`; mobile layout rules remain in place.

## Checks
- `node --check miniapp/app.js`: PASS
- `python -m compileall -q legal_bot`: PASS
- `python preflight.py`: PASS
- `pytest -q`: 105 passed
- Live Telegram/device visual validation: NOT performed.
