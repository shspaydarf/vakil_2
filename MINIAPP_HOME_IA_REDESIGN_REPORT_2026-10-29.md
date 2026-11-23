# LegalBot Mini App — Home Information Architecture & MACHINA UI Pass
Date: 2026-10-29

## Scope
Applied a low-risk Mini App home redesign to the provided `LegalBot_Mechanical_Elegance_MiniApp_2026-10-29-1.zip` source. This pass changes the home layout and theme layer only; it does not change API contracts, database schema, legal logic, Telegram bot menus, or law data.

## Changes
- Replaced the case-list-first home hero with a LegalBot legal-workspace hero and a direct-access tool area.
- Added four custom-shaped home tool buttons: legal Q&A, case analysis, evidence/issue review, and drafting/review.
- Tool buttons route into existing case-specific workflows after the user chooses an active case. The Q&A button opens the existing case AI, analysis opens the existing legal analysis, evidence/issue review opens the existing evidence view, and drafting opens the existing case drafting workflow.
- Added a case-selection modal that uses the existing case list and avoids inventing new API endpoints.
- Kept the case vault, search, active/archive filters, refresh, create-case action, and all case workspace controls available.
- Distinguished the bottom navigation actions: Home returns to the top of the home screen; Cases scrolls to the case vault; Account retains its existing behavior.
- Added a large AI Command Deck visual panel at the bottom of the home screen. Its button is intentionally disabled and clearly marked as awaiting activation; no fake backend action was added.
- Applied the agreed sage/silver/graphite palette, stronger steel borders, restrained champagne detailing, responsive tile layout, pressed-button feedback, and reduced-motion support.
- Added no images, external fonts, or new libraries.

## Safety and compatibility notes
- Existing case-related actions remain in the case workspace.
- The new home shortcuts use existing case-specific views; no general/public Q&A or drafting backend was fabricated.
- The AI Command Deck is visual-only and disabled until its real capability is activated.
- A readiness guard prevents opening a selected tool view if its case workspace failed to load, reducing the risk of showing stale case context.
- The existing Telegram authentication and API request patterns are unchanged.

## Verification
- `node --check miniapp/app.js`: PASS
- `python -m compileall -q legal_bot`: PASS
- `python preflight.py`: PASS
- `pytest -q`: 105 passed
- ZIP integrity: checked after packaging

## Not verified
- No live Telegram Mini App was opened, and no real Telegram/API integration test or multi-device visual test was performed in this environment.
- This is a UI/navigation pass, not a concurrency or load-test result.
