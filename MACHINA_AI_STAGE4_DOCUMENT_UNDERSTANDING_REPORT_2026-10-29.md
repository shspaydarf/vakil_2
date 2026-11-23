# MACHINA AI — Stage 4: Document Understanding Improvements

Date: 2026-10-29

## Scope

This is a low-risk improvement to the existing local-first chronology/document-understanding layer. No database schema, legal JSON data, external model prompt, provider/API contract, or case workflow was changed.

## Change made

When the chronology engine detects a possible date conflict between similar events, the conflict record now carries source-level evidence for both sides:

- event ID and normalized/display date;
- source document ID and document name;
- page number when present in extracted text;
- source snippet;
- character offsets when available;
- explicit `review_required: true` and `interpretation: possible_date_conflict` markers;
- a message that frames the result as a possible conflict requiring human review, not a final factual/legal conclusion.

This makes the conflict report more actionable: a reviewer can navigate back to the actual source material rather than seeing only event IDs and dates.

## Regression test

Added `test_timeline_date_conflict_includes_both_source_spans` to verify that a two-document date conflict includes both document names, page references, source snippets, and review-required semantics.

## Validation results

- `pytest -q`: **108 passed**
- `node --check miniapp/app.js`: PASS
- `python -m compileall -q legal_bot`: PASS
- `python preflight.py`: PASS (Python syntax, JSON parse, core files/data, callback fallback)

## Limitations

- This does not establish that the two dates truly conflict in the legal/factual sense; similar wording can describe different events. The result is explicitly labelled as a possible conflict and requires human review.
- This stage does not introduce a new AI model call and does not claim improved model reasoning. The change improves source traceability of an existing deterministic chronology feature.
- No live Telegram or browser/device validation was performed in this stage.
