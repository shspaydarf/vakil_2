# MACHINA — Hidden Extras (2026-10-29)

## Implemented
- **Microfastener 01 — Tiny Challenge:** four offline logic/number puzzles, answer feedback, and next-puzzle control.
- **Microfastener 02 — Quick Convert:** local-only conversions for length, weight, temperature, and volume; instant recalculation and swap-units control. No network requests or persistence.
- **Microfastener 03 — Ghost Circuit:** toggles decorative, low-intensity lights across the page and within its panel. A small ambient soundscape can be started/stopped explicitly by the user using Web Audio; no remote audio files or third-party service.
- Updated invisible controls' accessible labels; visible appearance remains camouflaged as mechanical fasteners.
- Motion respects `prefers-reduced-motion`. Audio is user-initiated and is stopped on page hide. No case, account, legal workflow, API, or database logic changed.

## Verification
- `node --check miniapp/app.js` — PASS
- `python -m compileall -q legal_bot` — PASS
- `python preflight.py` — PASS
- `pytest -q` — 105 passed
- ZIP integrity — checked after packaging

## Notes
- The ambient feature is a gentle synthesized tone bed generated locally in the browser, not a recorded music track. Browser/WebView audio support and real-device Telegram appearance have not been visually validated in this environment.
