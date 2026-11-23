# MACHINA — Pagani Mechanical Controls & Service Hatch

Date: 2026-10-29

## Scope
Follow-up visual interaction pass after the Pagani-inspired dashboard redesign. The goal is to make the dashboard feel like a coherent instrument fascia rather than a conventional card grid, while keeping the legal workflow and existing handlers unchanged.

## Changes
- Added a small copper service-latch control beside the home tools heading.
- The latch opens/closes a short decorative service drawer with a visible `aria-expanded` state and `aria-controls` relationship. Its message explicitly states that no data is changed.
- Added a short, reduced-motion-aware reveal animation for the drawer.
- Refined the instrument pods' bezel interaction on hover/focus-capable devices; each tool gets a slightly different ring geometry.
- Strengthened the copper pipe run around the instrument bank using CSS only; no image assets or external resources were introduced.
- Kept the mobile layout compact and the existing accessible focus styles intact.

## Safety / scope boundaries
- The new latch is decorative and does not call the API or mutate cases, documents, account state, or legal analysis.
- Existing tool buttons and their `data-tool` routing remain unchanged.
- No database, backend, API, law JSON, legal logic, or external dependency changes.
- No images or external fonts added.

## Validation
- `node --check miniapp/app.js`: PASS
- `python -m compileall -q legal_bot`: PASS
- `python preflight.py`: PASS (Python syntax, JSON, core files/data, callback fallback)
- `pytest -q`: 105 passed
- Live Telegram / real-device visual test: NOT performed; inspect in the target Mini App before release.
