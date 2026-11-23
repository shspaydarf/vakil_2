# MACHINA Batch 20 — Stage 3: Mini App Global Search UI

Date: 2026-10-31
Base: Batch 20 Stage 2 — Unified Search Engine

## Delivered

- Added a prominent Global Finder search panel to the Mini App home screen.
- Added a dedicated search results view backed by `GET /api/v1/search`.
- Added scope filters for cases, documents/versions, notes, tasks/events, AI history, drafts, clients, personal library, legal resources, and glossary.
- Added an opt-in archived-case filter; archived records remain excluded by default.
- Added grouped results, per-source result counts, snippets, case names, verified page/line indicators, locator metadata, and source/provenance notices.
- Added result navigation to the relevant case workspace and its document, note, task, draft, or AI section; client results open client management; law citations route to the existing legal-source detail view; personal-library results route to the personal library.
- Search remains local-first and uses the authenticated user-scoped Stage 2 API. No case text is sent to an external AI service.
- Added responsive styles consistent with MACHINA's light sage, steel, and champagne design language.

## Scope and safety

- No database schema changes.
- No change to the Stage 2 search engine or ranking behavior.
- The UI shows the API's coverage and privacy notes and does not imply that missing results prove information is absent from source files.
- Archived case results are only requested when the user explicitly enables the archived filter.
- Source navigation uses the existing ownership-protected case APIs.

## Validation

- `pytest -q`: **304 passed** (includes 3 new Mini App UI integration checks).
- `node --check miniapp/app.js`: PASS.
- `python -m compileall -q legal_bot`: PASS.
- `python preflight.py`: PASS.
- Live Telegram WebView/device rendering and navigation were not exercised in this environment.

## Next

Stage 4: test retrieval accuracy, cross-account isolation, archived-case behavior, source navigation, performance, and edge cases with representative data. Visual polish should be finalized against real Telegram screenshots after deployment.
