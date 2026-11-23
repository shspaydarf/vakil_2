# LegalBot — Low-risk architecture cleanup (2026-10-29)

## Scope
A deliberately conservative second cleanup pass. No bot handlers, API routes, database tables/migrations, Mini App assets, legal source datasets, callback IDs, or product features were deleted or renamed.

## Changes made
1. **Docker build-context hygiene:** `.dockerignore` now excludes Python pickle caches, local `.env` files (while allowing the example template), and audit/report/patch-note Markdown files that are not runtime dependencies. This reduces accidental inclusion of local artifacts and build context noise; source law JSON data remains included.
2. **API config import consolidation:** combined two imports from `legal_bot.config` into one. No behavior changes intended.

## Deliberately not changed
- No modules were removed based on static guesses; callback registration and dynamic imports make that too risky without broader runtime coverage.
- No legal JSON datasets/manifests were deleted.
- No requirements were removed because static search alone is insufficient proof of safe removal.
- No changes to Mini App, Telegram bot, API/database architecture, auth, migrations, or data retention.

## Verification
- `pytest -q`: **105 passed**.
- `python -m compileall -q legal_bot`: passed.
- `node --check miniapp/app.js`: passed.
- `python preflight.py`: passed.
- ZIP integrity: checked after packaging.

## Limitations
No live Telegram, production server, external AI, or Docker image build was run in this environment. This is a low-risk source/package hygiene pass, not a claim of live production validation.
