# MACHINA Lawyer Memory — Stage 4.4 Report

Date: 2026-10-31
Input baseline: `MACHINA_Lawyer_Memory_Stage4_3_Specialized_AI_Preferences_2026-10-31.zip`

## Scope

Stage 4.4 adds an explicit, deterministic precedence policy to the bounded preference context. It does not change the preference schema, storage model, authenticated UID flow, AI provider, or Mini App routes.

## Precedence encoded in the AI context

1. System/developer instructions, safety policies, and security limits.
2. Legal/factual correctness, available evidence and sources, and transparent uncertainty. The model must not fabricate laws, judgments, articles, quotations, facts, or sources.
3. The user's explicit request in the current turn, within the first two constraints.
4. Saved lawyer preferences, used as defaults only when the current request is silent or ambiguous.
5. Professional conventional output when no instruction applies.

Material unresolved conflicts should be surfaced briefly or clarified when necessary. Preferences are explicitly marked as style/format settings, not case facts or authority to bypass confidentiality.

## Implementation

- Updated `legal_bot/ai_preference_context.py` guard block.
- Added `tests/test_ai_preference_conflict_stage4_4.py` covering hierarchy, factual/source integrity, current-request precedence, default-only saved preferences, maximum-length safety, and omission of incomplete blocks.
- Existing 4.1–4.3 adapter and wiring remain unchanged.

## Verification

- Targeted Stage 4.1–4.4 tests: **21 passed**.
- Python compile check: PASS.
- ZIP integrity test: PASS.
- Full project pytest collection: BLOCKED by the baseline archive's missing `legal_bot/data/iran/legal_glossary.json`; 8 test modules fail during import for this same missing file. No substitute glossary was fabricated.

## Changed files

- `legal_bot/ai_preference_context.py`
- `tests/test_ai_preference_conflict_stage4_4.py`
- This report
