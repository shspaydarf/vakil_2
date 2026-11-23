# LegalBot — AI Main Menu/Submenu Patch

Date: 2026-10-28
Base: LegalBot Stage 5 Drafting Review ZIP available in the workspace.

## Changes
- Added `🤖 دستیار هوشمند` to the main Telegram inline menu (`menu_lawyer`) with callback `aimenu`.
- Added a dedicated AI submenu with the initial active capability: `💬 پرسش هوش مصنوعی درباره پرونده`.
- Added a case picker from the AI submenu; selecting a case routes to the existing case AI flow (`cai:<id>`), preserving its current consent and context-selection behavior.
- Renamed the case-menu entry from `پرسش از هوش مصنوعی` to `دستیار هوشمند پرونده`.
- Registered the new callbacks in `legal_bot/main.py`.
- No AI model behavior, data-sending policy, OCR behavior, or classic feature logic was changed in this patch.

## Validation
- `pytest -q`: 69 passed.
- `python preflight.py`: PASS.
- `python -m compileall -q legal_bot`: PASS.
- `node --check miniapp/app.js`: PASS.

## Scope note
This patch is based on the Stage 5 ZIP available in the workspace, not a live-server inspection. The submenu currently exposes the existing, working case-context AI flow only; no unwired AI helper is presented as an active feature.
