# MACHINA — Signature Shift Control

## Implemented
- Assigned the signature mechanical motion to the high-use **پرسش حقوقی** control.
- Added a small copper-and-steel gear-shift lever to that control. On tap/click, the lever moves forward with a short tactile motion, then the existing case-selection workflow opens.
- The lever is decorative and does not change API, database, case content, legal logic, or routing.
- Other tool buttons and all existing interactions remain unchanged.
- Responsive sizing and `prefers-reduced-motion` support included; lever is hidden from assistive technology because it is decorative.
- No images, external fonts, or dependencies added.

## Checks
- `node --check miniapp/app.js`: PASS
- `python -m compileall -q legal_bot`: PASS
- `python preflight.py`: PASS
- `pytest -q`: 105 passed
- Duplicate HTML IDs: none
- Live Telegram/device visual testing: not performed.
