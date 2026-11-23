# MACHINA Growth Batch 20 — Stage 2: Unified Local Search Engine

Date: 2026-10-31
Base: Batch 19 Visual Cohesion

## Scope delivered

Implemented the backend search engine and authenticated API contract for a single local-first search across a lawyer's private workspace and shared legal references. The Mini App's central search screen and filters are intentionally left for Stage 3.

### New module

`legal_bot/unified_search.py`

Supported scopes:
- `cases`: owned active case names/status and available case summary text.
- `documents`: extracted text from case documents and saved versions, with page/line provenance only when present in extracted text.
- `notes`: lawyer's private case notes.
- `tasks`: case tasks and case events.
- `ai`: saved question/answer history attached to owned cases.
- `drafts`: durable drafting artifacts and versions.
- `clients`: own client name and note only; phone and national ID are never indexed or returned.
- `library`: personal lawyer library items.
- `laws`: shared legal reference search via the existing local legal index.
- `glossary`: shared glossary lookup.

### API

Added authenticated endpoint:

`GET /api/v1/search?q=<query>&scopes=cases,documents,...&limit=40&archived=0`

- Query length: 2–200 characters.
- Result limit: 1–60.
- Scope list is allow-listed; unknown scopes are rejected.
- If `scopes` is omitted, all supported scopes are queried.
- `archived=1` explicitly includes archived case material; default excludes it.
- Response includes a unified result shape, source counts, source labels, case context, page/line locator where verified, and privacy/coverage notices.

### Privacy and provenance

- Private workspace SQL is scoped by the authenticated `uid` and joins through owned cases.
- No caller-supplied case/document IDs are accepted for the global query.
- Client phone numbers and national identifiers are excluded from search and response data.
- Search is deterministic/local-first; no AI provider is called and private text is not sent externally.
- Page numbers are only exposed from extracted page markers or the existing page-aware search helper. Missing pagination is not guessed.
- Legal references remain a separate shared-source category and their presence/ranking is not represented as proof of current validity or legal authority.

### Telegram global-search repair

The old global-search handler referenced an undefined `search_cases(...)` function. It now calls the unified search service for owned cases, documents, notes, and tasks, and displays source/case context. This removes the known undefined-function failure from that route.

## Validation

- `pytest -q`: **301 passed**.
- New unified-search tests: **6 passed**.
- `node --check miniapp/app.js`: PASS (Mini App UI was not changed in this stage).
- `python -m compileall -q legal_bot tests`: PASS.
- `python preflight.py`: PASS.
- ZIP integrity: checked after packaging.

## Known limitations / next stages

- Stage 2 delivers the search engine and API only. The Mini App search launcher, filter UI, grouped result cards, and navigation into source records belong to Stage 3.
- This is local lexical/hybrid-ready search, not a semantic embedding index. Search quality and ranking should be evaluated with representative Persian legal queries in Stage 4 before introducing optional semantic retrieval.
- Search only covers extracted text. Scanned files without OCR text and non-indexed content are not searchable.
- No live Telegram WebView, production DB corpus, load test, or multi-user deployment test was run.
- The search endpoint is bounded by row/result caps but no performance benchmark against a production-sized database was performed.
