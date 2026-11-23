# MACHINA — Stage 3: Hidden Mechanism Home

Date: 2026-10-29

## Goal
Move the home screen from a generic legal dashboard toward a bespoke mechanical control panel, while keeping the interface readable, responsive, and operational.

## Changes
- Refined the home hero into a light mint/silver instrument-panel surface with restrained copper registration marks and a small system label.
- Strengthened the four legal tool tiles with raised steel-like symbols, differentiated corner geometry, clearer contrast, and a tactile hover state.
- Developed the case archive into a subtle cabinet/vault-inspired surface using metallic edge details, file-card treatment, and a more prominent create-case control.
- Harmonized the disabled AI command deck and bottom navigation with the same bright metal, sage, and copper design language.
- Added responsive adjustments and preserved reduced-motion behavior.

## Scope and safety
- CSS-only update to `miniapp/styles.css`.
- No JavaScript, handlers, routes, DOM IDs, API, database, legal-analysis logic, or law JSON files changed.
- No images, remote fonts, new dependencies, or external assets added.

## Checks
- `node --check miniapp/app.js` — PASS
- `python -m compileall -q legal_bot` — PASS
- `python preflight.py` — PASS
- `pytest -q` — PASS: 105 passed

## Not performed
No live Telegram Mini App run, browser-based visual inspection, or real-device testing was performed. Final appearance should still be checked in the Telegram test environment before production release.

## Next
Stage 4: apply the same restrained mechanical design language to the case archive/workspace experience, without altering case workflows.
