# MACHINA Atelier Extras — 2026-10-29

## Added
- Decorative copper pipework in the home-page instrument rail, kept behind content and marked aria-hidden.
- Live device-local digital clock and localized Persian date, updated once per second.
- Mini calendar for the current device-local month, with today's date highlighted. It is a date display only; it does not claim to represent tasks or appointments.
- A clickable decorative vault latch that rotates and toggles a brief visual open/close state. Explicitly labeled as decorative and does not change authorization, encryption, or case data.
- A clickable calibration dial that rotates 135 degrees and shows a playful toast; it does not affect app functionality.
- Hidden maker's mark: five quick activations on the scales emblem trigger a short easter egg message and restrained motion.
- Reduced-motion rules, keyboard access for the maker's mark, and ARIA labels/states for interactive controls.

## Files changed
- `miniapp/index.html`: added instrument rail, clock/date/calendar, decorative latch and status message.
- `miniapp/app.js`: local clock/calendar rendering and isolated decorative interaction handlers.
- `miniapp/styles.css`: copper pipes, instrument panels, dial/latch states and restrained animations.

## Scope and safety
No API, database, legal logic, case workflow, permissions, or security controls changed. The vault animation is cosmetic only and must not be interpreted as a security feature. The calendar shows dates only and does not invent tasks. No images, external fonts, or dependencies were added.

## Checks run
- `node --check miniapp/app.js`: PASS
- `python -m compileall -q legal_bot`: PASS
- `python preflight.py`: PASS
- `pytest -q`: 105 passed
- ZIP integrity check: performed after packaging

## Not performed
No live Telegram Web App, real-device, or interactive browser visual test was performed. Responsive visual behavior should be checked in the target client before deployment.
