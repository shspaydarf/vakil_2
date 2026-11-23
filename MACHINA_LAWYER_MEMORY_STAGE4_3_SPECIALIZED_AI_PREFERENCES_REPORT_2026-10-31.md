# MACHINA — Lawyer Memory Stage 4.3

Date: 2026-10-31

## Scope

Specialize the already-connected lawyer preference context by AI workflow. This stage does not change model providers, credentials, legal retrieval, case ownership, Mini App endpoints, or the persisted preference schema.

## Implementation

- Added task-scoped preference allowlists in `legal_bot/ai_preference_context.py`.
- Supported task profiles: `case_analysis`, `legal_drafting`, `case_summary`, `contract_review`, `document_review`, `legal_question`, `general`, and `extraction`.
- The adapter now accepts an optional `task` argument while preserving the prior default behavior for callers that omit it.
- The AI feature dispatcher maps its application-controlled feature identifier to a task profile before loading the authenticated owner's preferences.
- Contract review receives document-review controls (focus areas, comparison mode, evidence display, missing-information behavior) without unrelated case-analysis controls.
- Drafting receives writing, analysis, citation, output-format, and interaction preferences without contract checklist controls.
- Case summary receives concise presentation/summary preferences without citation configuration.
- Machine transcription/extraction uses an empty preference category set to avoid presentation preferences steering extraction.
- Unknown feature identifiers use the conservative general profile. Free-text notes and professional/client/case context remain excluded.

## Tests

Focused tests:

`pytest -q tests/test_ai_preference_context_stage4_1.py tests/test_ai_preference_context_stage4_2.py tests/test_ai_preference_context_stage4_3.py`

Result: **15 passed**.

`python -m compileall -q legal_bot`

Result: **PASS**.

Full test collection was attempted. It is currently blocked by an input-package omission that predates this stage: `legal_bot/data/iran/legal_glossary.json` is referenced by `legal_bot/glossary.py` but is absent from the supplied Stage 4.2 ZIP. Eight test modules fail during collection for this same missing file. No placeholder glossary was fabricated and no unrelated legal-data file was modified.

## Stage status

Stage 4.3 implementation and focused verification: **COMPLETE**.

Stage 4.4 (preference conflicts with current user request, legal correctness, and system rules) remains pending. Stage 4.5 (integrated QA) remains pending and should include a complete source package with the missing legal glossary.
