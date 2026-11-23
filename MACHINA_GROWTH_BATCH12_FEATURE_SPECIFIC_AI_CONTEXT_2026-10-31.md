# MACHINA Growth Batch 12 — Feature-Specific AI Context Optimization

Date: 2026-10-31
Base: Batch 11 — AI Cost Optimizer

## Scope

This batch improves the case-question context assembly path. It does not change the AI provider, model, consent gate, entitlement reservation/commit/refund flow, or AI menu placement.

## Changes

- Added `legal_bot/ai_context_optimizer.py` with deterministic Persian/Arabic text normalization, question-term extraction, record relevance scoring, and page-level relevance selection.
- Structured Timeline, Issue, Evidence, and local-authority records are now selected as complete records against the lawyer's explicit question. Original record order and source metadata are preserved in the selected context. If lexical matches are absent, the selector uses a conservative leading-record fallback.
- Page-labelled document blocks can be selected by lexical overlap with the question, with original page markers retained and selected page numbers exposed in context coverage metadata.
- The AI request context now reports selection strategy and selected/available record/page counts so partial coverage is visible. The prompt explicitly warns that lexical page selection is not semantic search or complete document review.
- Structured records are not cut mid-JSON to meet the per-section budget; records that do not fit are omitted and the selection audit marks the omission.
- No text is paraphrased or summarized by the optimizer. No cross-user cache is introduced.

## Safety / limitations

- Lexical matching is a low-cost heuristic, not semantic retrieval. It may miss relevant passages expressed with synonyms or different wording.
- When no useful lexical overlap exists, the system falls back to the previous balanced document sample / deterministic leading records rather than claiming a focused result.
- The UI still requires human review; this batch does not claim complete review of every page when a subset is sent.
- The general legal Q&A path, standalone drafting flows, and OCR pipeline are unchanged.

## Verification

- `python -m pytest -q`: 259 passed
- `node --check miniapp/app.js`: passed
- `python -m compileall -q legal_bot`: passed
- `python preflight.py`: PASS
- ZIP integrity: checked after packaging

No live external AI call, provider-token benchmark, live Telegram test, or concurrent-user load test was performed. Token savings must be measured using provider-reported usage in the target deployment.
