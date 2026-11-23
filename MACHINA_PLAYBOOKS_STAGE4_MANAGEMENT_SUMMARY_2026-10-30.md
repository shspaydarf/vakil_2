# MACHINA Playbooks — Stage 4

## Scope
Added a deterministic management-summary section to the existing contract Playbook report. The summary is generated from already validated findings and the selected Playbook criteria/questions; it does not ask the model to invent a legal conclusion.

## Summary fields
- Number of criteria with at least one validated finding, out of total criteria.
- Count of validated findings by model-proposed risk level (high/medium/low).
- Criteria for which no sufficient quote-backed finding was returned.
- The selected Playbook's follow-up questions.
- An explicit warning that absence of a finding is not proof of compliance or absence of a defect.

## Safety and scope
- Existing quote validation remains unchanged.
- No database, law JSON, Gramophone, or unrelated AI-menu changes.
- No legal validity conclusion or definitive risk score is produced.
- Telegram and external-provider live integration were not exercised.

## Tests
`pytest -q`: **140 passed in 12.57s**.
One new test verifies summary counts, follow-up questions, and the conservative caveat.
