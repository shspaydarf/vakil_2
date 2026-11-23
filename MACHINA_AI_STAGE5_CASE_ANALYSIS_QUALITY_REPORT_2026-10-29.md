# MACHINA AI Stage 5 — Case Analysis Quality Pass

Date: 2026-10-29

## Scope

This is the next incremental slice of Stage 5, focused on the AI-assisted lawyer-facing case summary. It does not claim a full redesign of all specialized tools.

## Changes

- Added `_sample_case_text`, a bounded text sampler that includes excerpts from the beginning, middle, and end of long extracted case text, in document order, and explicitly labels omitted portions.
- Replaced the previous head/tail-only sample in `summarize_case_for_lawyer` with the distributed sampler. The existing request-size bound and single-call behavior remain.
- Strengthened the case-summary prompt to distinguish document-stated facts, party allegations, and analysis; report conflicting data separately; avoid equating absence from the supplied excerpt with nonexistence; and keep strengths/weaknesses evidence-based and non-conclusive.
- Added deterministic tests for distributed sampling and the summary prompt's evidence/uncertainty requirements.

## Compatibility and safety

- No database schema, law JSON, API contract, case workflow, consent gate, or model-call count was changed.
- The helper samples extracted text only; original documents and images are not passed to the external model by this change.
- Existing external-data consent remains required by `summarize_case_for_lawyer`.
- Long documents are still sampled to a configured size limit. This improves distribution of the sample but does not guarantee full-document coverage. The response continues to include a coverage note when sampling occurs.

## Validation

- `pytest -q`: **113 passed**.
- `python preflight.py`: **PASS**.
- `python -m compileall -q legal_bot`: **PASS**.
- `node --check miniapp/app.js`: **PASS**.
- No live external-model call or Telegram runtime validation was performed; model output quality still needs evaluation against the Stage 2 benchmark.

## Next recommended slice

Improve contradiction review by validating quoted evidence against the supplied extracted text and preserving page provenance where available, then add factual-preservation tests for rewriting/drafting outputs.
