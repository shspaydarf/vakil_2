# MACHINA Growth Batch 9 — AI Token & Cost Optimization

Date: 2026-10-31
Base: Growth Batch 8 — Persistent Workflow Builder

## Objective
Reduce external AI input/output cost and unnecessary calls while keeping the existing AI features, explicit external-data consent, source provenance, and lawyer review flow intact. This batch does not move classic tools into AI or add new AI features.

## Implemented

### 1. Removed redundant synthesis call from structured document extraction
- Each selected document chunk is still sent through the existing structured extraction prompt.
- Each chunk result is validated locally and must retain valid source-page provenance.
- Successful chunk outputs are merged deterministically in local Python code.
- The former additional AI synthesis request was removed because it repeated a merge that the application can perform deterministically.
- Result metadata now reports `ai_synthesis_calls_saved`, `ai_duplicate_paragraphs_removed`, processed chunks, and failed chunks.
- Expected direct saving: one external request per structured-analysis run, in addition to its input/output tokens. Actual currency savings depend on document size, model pricing, and provider usage reporting.

### 2. Conservative local duplicate-paragraph cleanup
- Removes only exact duplicate paragraphs within the same page before structured chunking.
- Page markers are preserved.
- Identical paragraphs on different pages are deliberately retained because repetition across pages may be meaningful evidence.
- No paraphrasing, summarization, OCR correction, legal inference, or source rewriting is performed.

### 3. Leaner local legal-source retrieval for Q&A
- Requests a wider candidate set from the local legal index, then ranks candidates using deterministic Persian keyword overlap with the user's question.
- Sends at most five ranked records.
- Each excerpt is capped at 900 characters rather than 1,800.
- Existing source-status labels, caveats, and source URLs are retained.
- If lexical matching finds no overlap, the prior top-five fallback is retained so retrieval does not silently return nothing.

### 4. Leaner legal-brief source pack
- Considers up to 20 locally supplied source candidates, then selects at most five using lexical overlap with the lawyer's fact narrative.
- Each source excerpt is capped at 1,400 characters.
- Source IDs are reassigned consistently to the actual selected source records; unsupported IDs remain guarded.
- Truncation is explicitly labelled so an excerpt is not mistaken for the full authority.

## What was intentionally not changed
- No automatic external AI calls were added.
- No change to the explicit external-data-consent gate.
- No images or original PDFs are sent by the normal text-only paths.
- No legal rule, deadline, date, amount, or fact is inferred locally as a substitute for source evidence.
- No shared or cross-lawyer prompt/result cache was introduced; that would create avoidable confidentiality and stale-result risks.
- No model, provider, or API key changes were made.
- No automatic shortening of the user's own question or facts was introduced.

## Verification
- Full pytest suite: **246 passed**.
- `node --check miniapp/app.js`: passed.
- `python -m compileall -q legal_bot`: passed.
- `python preflight.py`: PASS.
- ZIP integrity check: performed after packaging.

## Limits / next audit
- Token counts are not claimed as exact: the installed project does not currently record provider-reported prompt/completion token usage in a consistent per-feature ledger.
- No live provider calls were made, so cost savings are structural estimates, not measured invoices.
- No live Telegram/browser test or 200–300-user load test was performed.
- A later phase can add privacy-safe per-request token accounting using provider usage metadata (when available), plus per-feature cost dashboards and output-token ceilings tuned separately for summaries, Q&A, contract review, and drafting. Output caps should be introduced only with feature-specific quality tests so legal drafts are not silently truncated.
