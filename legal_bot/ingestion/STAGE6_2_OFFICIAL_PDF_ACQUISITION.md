# MACHINA Legal Engine — Phase 6.2: Official PDF Acquisition

## Outcome
The secure acquisition workflow is implemented and the live acquisition attempt is **blocked**, not successful.

The selected candidate's known URL (`https://rc.majlis.ir/fa/law/print_version/1014070`) is an HTML page URL, not a verified direct PDF asset URL. During this run, the execution environment could not resolve `rc.majlis.ir`; a web retrieval attempt also timed out. No direct official PDF asset URL could therefore be confirmed.

## Safety decision
- No mirror was substituted. FAOLEX remains discovery-only.
- No page URL was misrepresented as a PDF URL.
- No PDF bytes were acquired; no SHA-256 fingerprint or page count is claimed.
- No OCR, extraction, staging, validation, or active-bank import was run.
- The active JSON bank was not modified.

## Implementation
`official_pdf_acquisition.py` records an atomic acquisition manifest and fails closed unless a direct HTTPS `.pdf` asset URL on the exact official host `rc.majlis.ir` is supplied. It delegates actual byte acquisition to the existing `SecurePDFDownloader`, preserving its allowlist, public-IP, TLS, redirect, content-type, size, PDF-signature, and structural checks.

## Current manifest
`legal_bot/data/iran/ingestion/test_candidates/phase6_2_acquisition_manifest.json`

Status: `blocked`
Reason: `official_pdf_asset_url_unresolved`

## Next required action
Retry discovery/access to the official page from an environment with working DNS/network access, identify the direct PDF asset URL on `rc.majlis.ir`, and then rerun this workflow with downloads explicitly enabled. If the official endpoint remains unavailable, stop; do not use a mirror as an ingestion source.
