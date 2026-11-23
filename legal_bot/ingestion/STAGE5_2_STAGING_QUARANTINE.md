# Phase 5.2 — Isolated Staging and Quarantine Packages

## Scope
Create immutable-by-convention candidate packages in a separate ingestion area and validate their envelope/record structure. This phase is dry-run/staging only: it does not import, merge, normalize, or write to any active legal JSON bank.

## Package routing
- `legal_bot/data/iran/ingestion/staging/<candidate_id>/`: schema-valid candidates with an explicit Phase 4.6 `phase5_eligible=true` report. Status remains `staged_pending_human_review`.
- `legal_bot/data/iran/ingestion/quarantine/<candidate_id>/`: invalid candidates or candidates without a passing Phase 4.6 report.
- Existing package IDs are never overwritten. A collision raises `FileExistsError`.

## Package contents
- `candidate.json`: submitted envelope.
- `records.json`: record list, separated for downstream inspection.
- `schema_validation.json`: structural/integrity findings.
- `final_validation_report.json`: included when supplied.
- `package_manifest.json`: package state and safety flags.

## Validation contract
The envelope requires candidate/document identity, jurisdiction, authority and HTTPS source URL, source and extracted-text SHA-256 values, acquisition timestamp, original-PDF evidence path, pipeline version, validation-report references, a still-unapproved review decision, and a non-empty records list. Every record requires a unique ID, parent document match, locator, original text, positive source page references, and a SHA-256 matching its original text bytes.

Only known document kinds are accepted. Statutes, rulings, consultations, samples and circulars remain distinct classes. This schema check is not proof of authenticity, legal validity, currentness, or official status.

## Safety limits
- No active bank path is opened for writing.
- No source PDF is altered; its path and digest are retained as evidence references.
- No network access or download is initiated.
- No human approval is inferred. The package remains pending even when Phase 4.6 is eligible.
- Invalid or gate-blocked packages are quarantined, not silently discarded.
- Package creation uses a temporary sibling directory followed by atomic directory rename.

## API
`validate_candidate(candidate)` returns structural/integrity findings.
`create_candidate_package(candidate, data_dir=..., final_validation_report=...)` writes a package and routes it to staging or quarantine.
