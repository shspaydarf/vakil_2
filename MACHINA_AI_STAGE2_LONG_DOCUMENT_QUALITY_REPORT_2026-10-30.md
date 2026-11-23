# MACHINA AI — Stage 2: Long-document chunk quality

## Scope
Only the AI long-document text chunking path was changed. No UI, menu, database schema, legal JSON, or non-AI workflow was intentionally changed.

## Change
- Oversized page text is now split preferentially at paragraph, sentence, or whitespace boundaries rather than fixed character positions alone.
- A bounded overlap between adjacent chunks reduces the chance that a fact spanning a boundary is cut in half.
- Every chunk from a page retains the original `[صفحه N]` marker so existing page-provenance validation can still operate.
- The existing maximum-chunk cost ceiling and head/tail coverage behavior remain in place. If that ceiling is reached, `ai_truncated` continues to indicate that not all source chunks were processed; this is not presented as full-document coverage.

## Tests
- Added two tests for boundary-aware splitting, page-marker retention, and short-document behavior.
- Focused tests: 4 passed (including existing long-document merge tests).
- Full pytest suite: 125 passed.
- `python -m compileall -q legal_bot`: passed.
- `node --check miniapp/app.js`: passed.
- `python preflight.py`: passed.

## Limitations
- The hard maximum of 16 chunks remains to bound external model usage. Very large documents can still have unprocessed middle sections; `ai_truncated` must be surfaced or handled by the caller so users are not led to believe that coverage was complete.
- Automated tests use controlled inputs/mocks and do not establish live-model legal accuracy or OCR quality.
- No live Telegram deployment or external-model call was performed.
