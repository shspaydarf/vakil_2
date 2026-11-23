# MACHINA — Conservative Optimization Batch 1

Date: 2026-10-31
Base: `MACHINA_Conservative_Code_Cleanup_2026-10-31.zip`

## Scope and safety policy

This batch avoids deleting business logic, legal content, database fields, API routes, handlers, or Mini App behavior. The only runtime changes defer loading three JSON-backed reference indexes until the corresponding feature is first used. Existing lookup/normalization behavior is retained after the data is loaded. Missing or malformed data still raises an explicit error when that feature is called; the code does not silently substitute an empty legal dataset.

## Changes

1. `legal_bot/glossary.py`
   - Moved glossary file reading and normalization from module import to first non-empty lookup/expansion.
   - Added a thread lock so concurrent first requests do not build the index more than once.
   - Preserved `RAW_GLOSSARY` and `INDEX` as stable list objects.
   - Empty queries return immediately without opening the data file.

2. `legal_bot/important_terms.py`
   - Deferred phrase-index loading until a phrase/category helper is called.
   - Builds the `INDEX` and `BY_USE` lookup maps once under a lock.
   - Keeps missing/invalid source data explicit rather than silently ignoring it.

3. `legal_bot/knowledge.py`
   - Deferred official-source registry loading until a law/source registry lookup is requested.
   - Builds authority and law indexes once under a lock.
   - Keeps source verification status semantics unchanged.

4. Added focused regression tests:
   - `tests/test_glossary_lazy_loading.py`
   - `tests/test_important_terms_lazy_loading.py`
   - `tests/test_knowledge_lazy_loading.py`

## Validation

- Focused lazy-loading tests: **10 passed**.
- Python compile check for `legal_bot` and `tests`: passed.
- JavaScript syntax check (`node --check miniapp/app.js`): passed.
- Full test collection is still blocked by four tests importing `legal_bot.api`, which transitively requires `legal_bot/data/iran/laws.json`. That legal data file is absent from the supplied base ZIP. It was not fabricated or replaced.
- When those four test modules are excluded, the remaining suite reports **334 passed, 53 failed**. Most failures are also caused by the absent legal corpus (`laws.json`); one separate citation assertion mismatch remains. This is not a clean full-suite pass and must not be represented as one.

## Explicitly not changed

- `laws.py` and the legal corpus loading/indexing path: this is intentionally left untouched because the authoritative law data is missing from the supplied archive. Changing it to return empty results could make legal search appear successful while using no law corpus.
- No routes, permissions, database schema, legal JSON records, Telegram handlers, or Mini App UI were removed or rewritten.
- No dependency was removed from `requirements.txt`.

## Next safe audit candidates

- Recover the authentic `legal_bot/data/iran/` data directory from the canonical project source, then rerun all tests.
- Run a proper unused-import/static analysis tool in an environment where `ruff` or `pyflakes` is available. It was unavailable in this offline environment; imports were not removed based on guesses.
- Only after the data-backed suite is green, profile the large `api.py`, `db.py`, and `handlers.py` paths before considering refactors.
