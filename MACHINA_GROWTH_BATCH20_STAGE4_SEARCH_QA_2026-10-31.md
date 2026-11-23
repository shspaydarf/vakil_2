# MACHINA Growth Batch 20 — Stage 4: Search Quality, Security & Performance QA

Date: 2026-10-31  
Base: Batch 20 Stage 3 — Mini App Global Search UI

## Summary

Stage 4 completed a focused retrieval, ownership-isolation, archived-record, provenance, and synthetic performance audit. Several correctness issues were found and fixed before packaging.

## Fixes delivered

1. **Persian/Arabic normalization:** unified search now normalizes Arabic yeh/kaf variants, common Arabic alef forms, ZWNJ/ZWJ and direction marks, diacritics/tatweel, and Persian/Arabic digits before lexical matching.
2. **Empty scope handling:** an explicitly empty scope list no longer silently falls back to searching every scope. It returns no results; omitted scopes still use the documented defaults.
3. **No silent row-scan caps:** removed arbitrary per-source SQL row caps (500/1,200/300) that could hide older matching records before search. The API still caps displayed results at 60.
4. **Relevance ordering:** exact phrase matches and fuller token coverage receive a deterministic relevance bonus; ties prefer newer records.
5. **Transparent result counts:** response now includes `total_count`; per-source counts reflect all matches found before the display limit. The Mini App explicitly says “showing X of Y” when results exceed the display limit.
6. **Archived behavior:** archived records remain excluded by default and are included only when the explicit archived filter is enabled.

## QA coverage

- Persian/Arabic character variants, ZWNJ, diacritics, and Persian/Arabic digits.
- Owner isolation across documents, notes, tasks, events, AI history, drafts, clients, and personal library.
- Archived-case default exclusion and explicit inclusion.
- Verified page and line provenance from explicit page markers; no invented page labels.
- Older matching records beyond the former document scan cap.
- Exact phrase ranking above loose partial-token matches.
- Display limit versus total result count and per-source totals.
- API forwarding of authenticated UID, allow-listed scopes, clamped limit, and archived flag.
- Mini App UI disclosure of truncated results.

## Performance smoke test

Synthetic local SQLite corpus: **2,500 extracted-text documents** under one test account.  
Observed search time in this environment: **0.299 seconds** for a representative Persian query; 20 results returned, with the exact matching document ranked first.

This is a synthetic smoke benchmark, not a production load test. It does not establish performance under concurrent users, production-sized documents, or deployed hosting constraints.

## Validation

- `pytest -q`: **316 passed**.
- `node --check miniapp/app.js`: PASS.
- `python -m compileall -q legal_bot tests`: PASS.
- `python preflight.py`: PASS.
- ZIP integrity: checked after packaging.

## Known limitations

- Search remains local lexical retrieval with deterministic relevance scoring, not semantic embeddings or AI search.
- Only available extracted text is searchable. Scanned documents without OCR text, inaccessible attachments, and unindexed external content are not searchable.
- Shared legal-source search depends on the existing local legal index. A returned legal record is not proof that the provision is current, authoritative, or applicable; verify against the official source before relying on it.
- Result navigation opens the related case/workspace section. Exact in-place navigation to a particular historical AI message, event, or stored document version is not guaranteed by the current UI.
- No live Telegram WebView/device test, production database test, external legal-source freshness audit, or concurrent-user load test was performed.
