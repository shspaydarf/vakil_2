# Phase 7.7 — Human Review Gate

## Purpose
Create review packets for ingestion quality and record explicit human decisions in an append-only, hash-chained ledger. This is a data-quality control, not a legal opinion or a determination of a document's legal force.

## Added module
`human_review_gate.py`

- `build_review_packet(document, graph=None, policy=None)` checks source evidence, original-PDF hash/integrity metadata, extraction/OCR quality signals, parsed article structure, and supplied relationship-graph evidence.
- Findings are classified as `blocker` or `warning`. A packet with a blocker is `blocked`; otherwise it remains `awaiting_human_review`.
- The review checklist requires a human to check source identity, the original PDF visually, extracted/OCR text, article structure, and references/relationships.
- `record_review_decision(...)` records `approved_for_staging`, `rejected`, or `needs_correction`. Approval requires a non-blocked packet, all checklist items, reviewer identity, rationale, and evidence references.
- `verify_review_ledger(...)` validates the append-only hash chain.
- `write_review_artifact(...)` atomically writes only 7.7 packets/ledgers to a caller-selected path.

## Safety boundaries
- An approval means only that the specified ingestion data-quality review was completed and may proceed to a separate staging step.
- It does not establish legal validity, enforceability, current force, amendment, repeal, or official-source status.
- A secondary source remains secondary; this module cannot promote source authority.
- No network calls, PDF downloads, active-bank writes, or automatic legal decisions occur.
- A blocker cannot be bypassed by checking checklist boxes; the input must be corrected and a new packet generated.
- Prior ledger events are retained unchanged; edits invalidate the ledger hash chain.

## Inputs
The module consumes caller-supplied document metadata and optional 7.6 relationship graph. It does not fetch or infer missing evidence. The caller should provide `pdf_metadata`, `extraction_metrics`, `ocr_metrics`, `structure`, and explicit `source_evidence` where applicable.

## Test scope
Unit tests use synthetic fixtures. They validate packet generation, blocking conditions, OCR warnings, authority preservation, approval requirements, ledger tamper detection, relationship evidence checks, and atomic artifact writing. They do not establish the authenticity or legal status of real-world documents.
