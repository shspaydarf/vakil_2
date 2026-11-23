# MACHINA AI Stage 4 — Contract Review Helper

## Scope
This stage adds a conservative contract-review helper to `legal_bot/ai.py`. It does not change the traditional Gramophone area, other app menus, database schema, or legal JSON files.

## Implemented
- New `review_contract_risks(extracted_text, contract_type='نامشخص')` service helper.
- Enforces existing AI enabled / API key / external-data consent guards.
- Rejects empty extracted text.
- Uses bounded input with explicit coverage warning if truncation occurs.
- Requests structured risk candidates for clauses, but labels them as preliminary review suggestions, not legal conclusions.
- Verifies every retained quoted clause against normalized supplied text; unsupported quotes are discarded.
- Limits findings to eight, constrains risk labels, and caps displayed fields.
- Explicitly warns that absence from extracted text does not prove absence from the complete contract and that no legal validity conclusion is guaranteed.

## Not implemented in this stage
- This helper is not yet connected to a new visible Telegram/Mini App button or a new route. That is intentionally deferred to a separately scoped integration step so the UI and unrelated workflows remain unchanged.
- No live model request, real contract benchmark, or external legal-source validation was performed.
- The review is not a substitute for full-document review by a qualified lawyer.

## Validation
- `pytest -q`: 130 passed.
- `python -m compileall -q legal_bot`: passed.
- `node --check miniapp/app.js`: passed.

## Changed files
- `legal_bot/ai.py`
- `tests/test_ai_stage4_contract_review.py`
- This report
