# LegalBot MACHINA — Stage 4: Case Workspace

## Scope
- Updated the visual hierarchy of the case workspace header, status, next-action row, stats, quick actions, case metadata, and workspace feature cards.
- Kept existing API endpoints, case data, document flows, legal logic, database behavior, and AI calls unchanged.
- Made the existing “مسائل” card an explicit “مسائل و ایرادها” entry point to the current evidence/issues view, with keyboard activation support. This avoids leaving a visible card with no action while reusing an existing destination.
- Maintained responsive layout and reduced-motion support.
- No images, external fonts, new libraries, or remote assets added.

## Validation
- `node --check miniapp/app.js`: PASS.
- `python -m compileall -q legal_bot`: PASS.
- `python preflight.py`: PASS.
- `pytest -q`: 105 passed.
- Live Telegram and real-device visual tests were not performed.
