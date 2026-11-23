# MACHINA AI Playbooks — Stage 3

## Deliverable
Criterion-by-criterion contract review reporting for the three built-in Playbooks.

## Changes
- `legal_bot/ai.py`: asks the model to associate each finding with an allowed Playbook criterion ID.
- Only findings with quotes that can be matched to the extracted contract text are retained.
- The report now lists every Playbook criterion, marks criteria with a verified finding, and explicitly labels criteria without a verified finding as requiring review / lacking sufficient evidence in the reviewed text.
- Findings without a valid criterion association remain visible as unmatched findings rather than being silently discarded, provided their quote is verifiable.
- Existing no-Playbook output behavior remains available.

## Safety and scope
- No database/schema changes.
- No law JSON or legal-source changes.
- No Gramophone or non-AI menu changes.
- No original files are sent; the existing extracted-text workflow remains in use.
- A criterion without a finding is not labeled compliant or risk-free. Truncation warning remains in the report.
- Live Telegram and external-model end-to-end validation were not performed.

## Verification
- `pytest -q`: 139 passed in 13.84s.
- `python -m compileall -q legal_bot`: completed successfully.
