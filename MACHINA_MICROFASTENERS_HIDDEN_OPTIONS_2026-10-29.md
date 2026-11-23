# MACHINA — Micro-fasteners & Hidden Future Options

## Implemented
- Added three visually camouflaged, screw-like micro-controls to the decorative atelier instrument panel. They have no visible labels, but retain accessible names for screen readers.
- Each control currently triggers a small Persian placeholder toast only. They do not modify case data, account settings, legal outputs, API behavior, or persistence. Their future actions can be assigned later.
- Added more dimensional metal shading and shadow depth to decorative copper pipe fittings, consistent with the sculpted Pagani-inspired hardware.
- Controls have tactile hover/press states and respect reduced-motion preferences.

## Validation
- `node --check miniapp/app.js`: PASS
- `python -m compileall -q legal_bot`: PASS
- `python preflight.py`: PASS
- `pytest -q`: 105 passed
- No image assets, fonts, or dependencies added. No database/API/legal logic changes.
- Live Telegram/device visual validation was not performed.
