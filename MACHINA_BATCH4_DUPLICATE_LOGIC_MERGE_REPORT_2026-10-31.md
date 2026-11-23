# MACHINA — Batch 4: Conservative Duplicate Logic Merge

Date: 2026-10-31
Base: `MACHINA_Low_Risk_Cleanup_Batch3_2026-10-31.zip`

## Scope

This batch consolidates only repeated, identical low-level text helpers. It does not remove product features, routes, handlers, legal rules, legal data, or database behavior.

## Changes

Added `legal_bot/text_utils.py` with shared implementations for:
- whitespace cleanup (`clean_whitespace`), preserving the prior `str(value or "")` behavior;
- Persian character/case normalization (`normalize_persian_text`);
- normalized term matching (`has_any_normalized_term`);
- legal corpus title lookup (`find_law_source_hits`), preserving result shape and per-tree limits.

Updated the following production modules to reuse the shared helpers:
- `authority_engine.py`
- `rewrite_engine.py`
- `evidence_engine.py`
- `adversarial_review.py`
- `issue_engine.py`
- `timeline_engine.py`
- `strategy_engine.py`
- `draft_engine.py`
- `brief_information.py`
- `consistency_gate.py`
- `contract_tree.py`
- `ejare_tree.py`
- `claims_tree.py`
- `check_tree.py`
- `property_tree.py`

Added `tests/test_shared_text_utils_batch4.py` for the shared helper behavior, including result limits and malformed article payload handling.

## Duplicate audit

An AST-based exact-body audit of production Python functions found:
- Before: 8 groups / 26 function definitions involved in exact duplicates.
- After: 3 groups / 7 function definitions involved in exact duplicates.

The remaining duplicate groups were deliberately left untouched because they involve pagination or credit/entitlement behavior and need separate contract-level review.

## Validation

- `python -m compileall -q legal_bot tests/test_shared_text_utils_batch4.py`: passed.
- Focused tests: 11 passed.
- Three API-level tests could not complete because the base ZIP does not contain `legal_bot/data/iran/laws.json`; importing the API loads `legal_bot/laws.py`, which opens that missing source file. No placeholder legal data was created.
- An additional product/AI test run was likewise blocked at import time by the same missing `laws.json` dependency; this is a baseline packaging/data issue, not evidence of a regression from this batch.

## Safety notes

- Existing per-tree source-hit limits are preserved at call sites.
- The shared helpers have no dependency on the legal corpus, database, Telegram, or API modules.
- No legal source files or JSON law-bank files were changed.
- No feature or route was deleted.
- This batch is a conservative refactor, not a full production-readiness sign-off.
