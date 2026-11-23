# MACHINA Phase 4.7 — Integration Orchestrator

## Purpose
Phase 4.7 connects the existing PDF pipeline (3.7) to validators 4.1–4.5 and the fail-closed final gate (4.6). It introduces adapters for the real staging schema (`document_text`, `structure`, `pages`, `source`) and writes independent validation sidecars.

## Entry points
- `run_document_validation(...)`: process an already acquired local PDF and run the full validation bundle.
- `process_queued_candidate(...)`: explicitly download one queued candidate through `SecurePDFDownloader`, persist its download manifest, update queue acquisition state, then run the same validation bundle.

## Required evidence
- Candidate record from a connector (`source_id`, `page_url`, `asset_url`, title/type and available metadata).
- Download manifest produced by the secure fetcher (SHA-256, final source URL and acquisition timestamp).
- Source comparison records with source metadata and source text. These are supplied by the caller; Phase 4.7 does not silently fetch web pages.

## Outputs
- `05_staging_document.json` (Phase 3.7)
- `06_provenance_report.json`
- `07_metadata_report.json`
- `08_completeness_report.json`
- `09_version_conflict_report.json`
- `10_source_match_report.json`
- `11_final_validation_report.json`
- `12_integration_manifest.json`

## Safety boundaries
- Network downloads remain disabled by default in `ConnectorPolicy`.
- No CAPTCHA/challenge bypass is implemented.
- Official-source matching uses supplied source records; no live source access is claimed.
- Source matching is only a candidate corroboration, not official confirmation.
- Human approval requirements in 4.6 remain in force.
- No code path writes to or mutates the active JSON legal bank.
