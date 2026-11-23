# MACHINA AI Stage 3 — Conservative Local Legal-Source Retrieval

Date: 2026-10-30

## Scope

Changes are limited to the general legal Q&A path in `legal_bot/ai.py` and focused tests. No database schema, legal JSON data, Mini App UI, Telegram routing, or non-AI feature was changed.

## Changes

- General legal Q&A attempts local legal-source retrieval only when the user's question explicitly signals Iranian jurisdiction/law.
- Up to five locally retrieved records may be added to the prompt, with available title, locator, stored verification label, registered source URLs, and a bounded excerpt from existing text fields.
- Prompt context explicitly says that retrieval ranking does not establish applicability or current validity, and asks the model to use only what the supplied text supports.
- Retrieval errors are fail-open: they do not prevent answering the original question.
- For questions without explicit Iranian-law scope, local legal retrieval is not invoked, avoiding silent jurisdiction assumptions.
- No live web retrieval was added; legal JSON files and source registry were not modified.

## Validation

- Focused legal-Q&A tests: 6 passed.
- Full test suite: 127 passed.
- `python -m compileall -q legal_bot`: PASS.
- `python preflight.py`: PASS.
- `node --check miniapp/app.js`: PASS.

## Limitations

- This is retrieval from the existing local corpus, not live legal research.
- Registry labels and source URLs are passed through as stored; this patch does not independently validate whether a source is current, official, applicable, or substantively supports a legal conclusion.
- Retrieval relevance and actual model answer quality still require expert-reviewed benchmark cases and live-model testing.
