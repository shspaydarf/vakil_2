# MACHINA AI Stage 1 — Output Quality Pass

Date: 2026-10-29
Scope: Digital AI menu only; the change is limited to the shared final display pass used by the general AI-question dispatch path. No Gramophone/legacy menu, law JSON, database schema, API contract, or unrelated Mini App UI changes were made.

## Implemented

- Added `prepare_ai_answer()` in `legal_bot/text_guard.py` as a conservative display-only final pass.
- Reuses existing Persian typography cleanup and known internal pipeline-marker removal.
- Collapses only immediately adjacent, exactly identical non-empty lines; it does not deduplicate repeated lines elsewhere in an answer.
- Reduces excessive blank lines while preserving paragraph boundaries.
- Preserves legal content and numeric tokens; existing bidi isolation is retained for Telegram readability.
- Applied the pass to the general AI question response before sending it to the user and before storing the case AI exchange, so the displayed and stored response match.
- Empty/internal-only output is treated as a failed answer, preserving the existing refund/error path rather than charging for a blank result.

## Safety boundaries

This is a presentation cleanup, not legal verification. It does not validate legal citations, infer missing facts, rewrite conclusions, or claim the answer is fact-checked. No source text or case material is sent to a new external service. Existing consent and entitlement checks remain in place.

## Validation

- New focused tests: 4
- Focused AI/output tests: 10 passed
- Full automated suite: 123 passed
- `python -m compileall -q legal_bot`: passed
- `node --check miniapp/app.js`: passed

These are automated local checks. No live Telegram deployment, external model quality benchmark, or production integration test was performed.

## Remaining items for later stages

- Semantic quality scoring against a curated legal benchmark.
- Citation/source verification and retrieval from authoritative up-to-date legal sources.
- Cross-document factual consistency and deeper semantic contradiction checks.
- User-facing quality feedback and richer export-quality checks.
