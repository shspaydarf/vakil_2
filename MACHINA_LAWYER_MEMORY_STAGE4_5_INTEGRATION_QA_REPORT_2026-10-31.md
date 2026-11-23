# MACHINA Lawyer Memory — Stage 4.5 Integration QA Report

Date: 2026-10-31  
Input baseline: `MACHINA_Lawyer_Memory_Stage4_4_Conflict_Policy_2026-10-31.zip`

## Scope

Final integration QA for Lawyer Memory stages 4.1–4.5. The review covered the bounded preference adapter, task-specific profiles, conflict policy, AI call wiring, authenticated owner UID propagation, extraction isolation, and graceful fallback behavior.

## Findings and corrections

1. **Machine extraction was mapped to a presentation profile.** `document_structured_extraction` was routed to `case_analysis`, which could attach style preferences to a machine-oriented extraction operation. It is now mapped to the dedicated `extraction` task, which intentionally returns no preference context. `scan_vision_transcription` remains similarly isolated.
2. **Verified summary did not accept or forward the authenticated lawyer UID.** `verified_summary` now accepts an optional keyword-only `preference_uid` and forwards it to `_call_feature`, allowing owner-scoped summary preferences where the caller supplies an authenticated UID. Existing callers without a UID preserve legacy behavior.

No preference schema, storage model, authentication mechanism, provider configuration, Mini App route, or unrelated workflow was changed.

## Integration checks

- Task-profile routing for legal question, drafting, contract review, case summary, document review, verified summary, and text-assist drafting.
- Extraction/transcription isolation from presentation preferences.
- Verified-summary UID propagation.
- No-UID legacy prompt behavior.
- Existing adapter, task-specific profile, precedence, and context-wiring regression tests.

## Verification results

- Stage 4.1–4.5 focused integration suite: **25 passed**.
- Broader preference/store/security/service/contract-review selection: **62 passed, 3 failed during import** because the input archive does not contain `legal_bot/data/iran/legal_glossary.json`. The failures occur before the affected API/auth tests execute; no glossary was fabricated or substituted.
- Python compilation: PASS.
- ZIP integrity (`unzip -t`): PASS.

## Remaining release note

The missing `legal_glossary.json` is a pre-existing baseline packaging gap and prevents claiming a fully green project-wide QA run. Restore the authentic project glossary from the canonical source before a full release test. This stage does not create or modify legal-source data.

## Changed files

- `legal_bot/ai.py`
- `tests/test_ai_preference_integration_stage4_5.py`
- This report

## Stage 4 status

- 4.1 Secure preference adapter: complete
- 4.2 AI call wiring: complete
- 4.3 Task-specific preference profiles: complete
- 4.4 Conflict precedence policy: complete
- 4.5 Integration QA and regression checks: complete, with the documented baseline glossary limitation
