# MACHINA AI Stage 3 — Long-document coverage and resilient merge

Date: 2026-10-29

## Scope
This patch follows the agreed Stage 3 priority: preserve broad coverage when analyzing long extracted case documents and avoid losing successful chunk-level evidence if the final AI synthesis call fails.

## Changes

1. **Removed early prefix-only hard truncation in `structured_analysis`.** Previously, text longer than `AI_MAX_CHARS` was sliced from the beginning before page-aware chunk selection. This could remove the tail before the chunk selector had a chance to preserve broad coverage. The function now passes the complete locally extracted text to `_chunks`; the existing bounded chunk policy still limits model calls and marks the result as truncated when the chunk cap is exceeded.
2. **Added deterministic, provenance-aware merge fallback.** `_merge_extracted_results` combines successful chunk outputs while retaining only records that carry `source_pages`, and deduplicates only exact matches (including source pages).
3. **Made synthesis fail-safe.** The deterministic merge is prepared before calling the model. If synthesis fails, or the serialized chunk payload is too large for the bounded synthesis prompt, the combined chunk results are retained rather than falling back to only `extracted[0]`.
4. **Guarded against lossy synthesis.** A synthesis result replaces the deterministic merge only if its validated record count is at least as large as the fallback, reducing the chance that synthesis silently drops entire groups of extracted evidence.
5. **Added regression tests** for synthesis outage and broad head/tail page coverage.

## Files changed
- `legal_bot/ai.py`
- `tests/test_ai_stage3_long_document_merge.py` (new)

## Validation
- `pytest -q`: **107 passed**
- `node --check miniapp/app.js`: **PASS**
- `python -m compileall -q legal_bot`: **PASS**
- `python preflight.py`: **PASS** (syntax, JSON, core files/data, callback fallback)
- No external AI API calls were made during tests; model behavior was mocked.
- No live Telegram or browser validation was performed.

## Remaining limitations
- The chunk policy is still bounded (maximum 16 chunks) and intentionally omits some middle chunks for very large inputs; the result carries `ai_truncated=True`. This patch improves broad coverage and failure recovery but does not claim complete review of arbitrarily large files.
- `summarize_case_for_lawyer` and `review_case_contradictions` still use bounded head/tail sampling. A later focused change should consider multi-pass, page-referenced summaries and contradiction review while preserving cost and consent controls.
- This stage does not alter law JSON, database schema, API contracts, or legal source data.
