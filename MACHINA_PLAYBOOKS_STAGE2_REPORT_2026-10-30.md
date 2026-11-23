# MACHINA AI Playbooks — Stage 2

## Scope
Connected the three built-in contract playbooks (construction, lease, sale) to the existing AI contract-review callback in the digital/AI workflow only.

## Changes
- `legal_bot/handlers.py`: first `aicontract:<case_id>` click now displays a playbook picker; selecting `aicontract:<case_id>:<playbook_id>` validates the playbook and then runs the existing consent-gated contract review.
- `legal_bot/ai.py`: `review_contract_risks` accepts an optional playbook payload and injects its checklist labels into the review prompt. Existing evidence-quote validation, truncation behavior, entitlement reservation/commit/refund and consent checks remain in place.
- `legal_bot/main.py`: callback pattern now accepts the optional playbook identifier.
- `tests/test_ai_stage5_workflow_handoff.py`: updated callback registration assertion for the extended callback format.

## Safety and boundaries
- No database schema or data migration.
- No law JSON or legal-source changes.
- No Gramophone or non-AI menu changes.
- The original file/image is not sent; the existing extracted-text workflow is used.
- Playbooks remain built-in and static; user-defined templates, persisted review results, deterministic risk scoring and version history are not included.
- Live Telegram and external model end-to-end behavior were not tested.

## Verification
- `pytest -q`: 138 passed in 12.79s.
- `python -m compileall -q legal_bot`: completed successfully.
