# MACHINA Legal Engine — Phase 4.6

## Final validation decision gate

This phase consolidates the evidence from phases 4.1–4.5 into a single,
versioned JSON decision report. It does not certify legal authenticity,
determine whether an instrument is in force, or import anything into the
active law bank.

### Required evidence

- `provenance`: source catalog, acquisition chain and hash consistency.
- `metadata`: title, issuer, number and date screening.
- `completeness`: page and legal-structure completeness screening.
- `version_conflict`: duplicate/version relationship screening.
- `source_match`: comparison with supplied official/secondary source records.

Missing reports fail closed. Critical/high findings block the hand-off. Medium
findings or unresolved version relationships require human review. Even when
automated checks are clean, a complete human decision is mandatory.

### Human decision contract

`human_decision` must include:

- `approved`: boolean true;
- `reviewer_id`: non-empty reviewer identifier;
- `decided_at`: parseable ISO-8601 timestamp.

A human decision cannot override missing evidence, critical provenance/hash
problems, or absence of an official-source match candidate.

### Output

Write the result as `08_final_validation_report.json` beside the staged
validation artifacts. `phase5_eligible=true` means only that the document may
be handed to the controlled Phase 5 review/import workflow. It does not perform
an import. `active_bank_changed`, `import_performed`,
`official_confirmation`, and `legal_validity_proven` remain false.

### Limitations

The gate evaluates the supplied reports and does not independently fetch live
sources. The quality of its conclusion is bounded by the quality and provenance
of the upstream evidence. Human review must compare the original PDF and the
relevant official publication before any active-bank change.
