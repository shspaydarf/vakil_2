# MACHINA Growth Batch 13 — Case Context Cache

Date: 2026-10-31
Base: Growth Batch 12 — Feature-Specific AI Context

## Purpose
Reduce repeated local computation when a lawyer asks multiple AI questions about the same case. This is a deterministic intelligence cache, not a cache of AI answers and not a persistent case-memory feature.

## Implemented
- Added `legal_bot/core/case_context_cache.py`.
- Caches deterministic case intelligence snapshots: chronology, issues, evidence matrix, local guidance, candidate authorities, and compact intelligence summary.
- Cache key is scoped by `(user_id, case_id)`; no cross-lawyer or cross-case reuse.
- Fingerprint covers current case metadata, document IDs/timestamps/page counts and SHA-256 hashes of extracted text, plus case event details.
- Fingerprint mismatch invalidates the previous entry; a 120-second TTL also bounds staleness.
- Cache is process-memory-only, capped at 128 entries, and cleared automatically on process restart.
- Defensive copies prevent a caller from mutating the cached snapshot.
- Question-specific record selection, page selection, context budgeting, consent checks, AI calls, and token metering remain fresh on every request.
- No raw prompt, AI response, or persistent cache table is created by this feature.

## Safety / limitations
- Cached values are derived case intelligence and may contain case-sensitive facts while resident in process memory. They are not written to disk by this cache.
- This cache is per application process. Multiple workers may each compute their own copy; this is safe but may reduce the cache-hit rate.
- The cache avoids recomputing local engines; it does not itself guarantee a reduction in provider token usage. Token reduction still comes from the existing feature-specific context selection.
- The 120-second TTL limits stale local derived data. Document content hashes and case-event changes invalidate earlier entries on the next request.
- AI is never invoked by opening a case or populating the cache.

## Verification
- Full test suite: **263 passed**.
- Focused cache + AI + evidence/timeline tests: 17 passed.
- `node --check miniapp/app.js`: passed.
- `python -m compileall -q legal_bot`: passed.
- `python preflight.py`: PASS.
- ZIP integrity check: passed.
- No live Telegram test, external AI provider test, or concurrent-user load test was run.
