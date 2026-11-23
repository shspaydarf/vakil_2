# LegalBot MACHINA — Stage 2: Hidden Mechanism Design System

Date: 2026-10-29

## Purpose
This is the second stage of the new MACHINA design direction, applied directly to the existing integrated LegalBot project. It is not a separate app. The goal is a cohesive “hidden mechanism” look: bright mint-green surfaces, polished steel controls, warm copper details, and dark readable text, without making dark green a dominant color.

## Changes made
- Updated the semantic MACHINA color tokens to prioritize light sage/mint, silver, steel, copper, and champagne.
- Added layered metallic gradients and tactile raised-control shadows to existing primary/secondary actions and controls.
- Refined the four home tool tiles with restrained, varied corner geometry rather than making every control a plain rectangle.
- Added copper accents to the case-vault heading, timeline markers, active navigation indicator, warning/citation surfaces, and selected details.
- Kept typography and control text dark for contrast; copper is an accent rather than a large text/background color.
- Preserved reduced-motion overrides and small-screen adjustments.

## Scope and safety
- Changes are CSS-only in `miniapp/styles.css`.
- No JavaScript, API, database, legal-analysis logic, or law JSON files were changed.
- No images, remote fonts, new dependencies, or external assets were added.
- Existing DOM IDs, buttons, and routes were not intentionally altered.

## Checks run
- `node --check miniapp/app.js` — PASS
- `python -m compileall -q legal_bot` — PASS
- `python preflight.py` — PASS (Python syntax, JSON parse, core files/data, callback fallback)
- `pytest -q` — PASS: 105 passed

## Not performed
- No live Telegram Mini App test, real-device visual inspection, or interactive browser screenshot test was performed. The visual appearance should be verified in the Telegram test environment before production release.

## Next stage
Stage 3: redesign the home screen into the “mechanical control panel” concept and shape the case archive into a vault-inspired interaction, while retaining current routes and workflows.
