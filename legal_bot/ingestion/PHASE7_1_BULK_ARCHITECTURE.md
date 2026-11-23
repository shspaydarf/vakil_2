# MACHINA Phase 7.1 — Bulk Processing Architecture

## Scope
Phase 7.1 defines the control-plane architecture and a deterministic, bounded
batch planner. It does **not** discover sources, access the network, download
PDFs, run OCR, write staging packages, or modify active legal JSON files.

## Architecture
- **Control plane:** source registry, document catalog, bounded queues, job state,
  checkpoints, retry metadata, audit events and resource budgets.
- **Data plane:** immutable original PDFs plus separately stored extraction, OCR,
  normalized text, structure and validation artifacts.
- **Worker lanes:** discovery → acquisition → extraction/OCR → legal structuring
  → validation/human review → shadow search evaluation → controlled activation.
- **Isolation:** active bank, staging, quarantine and archive remain separate.
- **Backpressure:** document count, total bytes, OCR-page budget and per-source cap.
- **Recovery:** deterministic job identity, idempotent steps, checkpoints, bounded
  retries and explicit resume; no automatic retry loop in this phase.

## Planning contract
`create_batch_plan()` accepts pre-discovered candidate metadata. Only candidates
classified `official_primary` are eligible by default. Secondary and unverified
sources are rejected unless a caller explicitly changes the policy; such a policy
change does not make those sources official. Duplicate identities are skipped;
conflicting metadata for one identity is rejected. Capacity overflow is deferred,
not discarded. Ordering is deterministic.

## Default safety posture
- network access: disabled
- downloads: not started
- PDF/OCR processing: not started
- staging writes: not started
- active-bank writes: prohibited
- secondary-source substitution: prohibited by default

## Phase boundaries
7.2 establishes and validates source authority/host policy; 7.3 builds the document
catalog; 7.4 implements secure batch acquisition; 7.5 adds scalable extraction/OCR;
7.6 structures legal content and lineage; 7.7 validates and routes human review;
7.8 evaluates in an isolated search shadow; 7.9 handles explicitly approved,
transactional activation and operational monitoring.

A passing software test is not evidence of legal authenticity, current force of
law, or successful live access to Parliament sources.
