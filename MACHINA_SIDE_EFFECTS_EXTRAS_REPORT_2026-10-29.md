# MACHINA — Side Effects / Atelier Extras

Date: 2026-10-29

## Goal
Add a few deliberately unnecessary-but-fun decorative details and subtle motion while preserving clarity, accessibility, and existing behavior.

## Changes
- CSS-only section calibration marks.
- Soft breathing indicator lamp on the existing decorative hero icon.
- Fine halo around the existing radar-like issues symbol, reacting only to hover where supported.
- Short highlight sweep on tool tiles, triggered by hover/focus rather than continuously.
- Tiny copper fasteners on case cards and an accent along the archive rail.
- A slow dashed calibration ring around the existing AI-deck mark; the disabled feature remains visibly disabled.
- Reduced-motion overrides and small-screen adjustments.

## Scope and safety
- Changed only `miniapp/styles.css` plus this report.
- No HTML, JavaScript, API, database, legal logic, or law data changes.
- No images, external fonts, packages, or dependencies added.
- Decorative effects do not indicate that a legal operation succeeded.

## Verification
- `node --check miniapp/app.js`: PASS
- `python -m compileall -q legal_bot`: PASS
- `python preflight.py`: PASS
- `pytest -q`: 105 passed
- ZIP integrity: checked after packaging

## Limitations
No live Telegram Mini App or physical-device visual test was performed. CSS effects should be visually checked in Telegram on representative small and large screens before production release.
