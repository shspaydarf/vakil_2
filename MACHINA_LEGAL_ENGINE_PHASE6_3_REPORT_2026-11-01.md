# MACHINA Legal Engine — Phase 6.3 Report

## Scope
Implemented a fail-closed validator for the evidence package produced by Phase 6.2. It checks candidate identity, expected title, official HTTPS PDF endpoint, acquisition status, mirror prohibition, local original-file presence, PDF signature, SHA-256, PDF structural validity, and page-count consistency when present.

## Critical operational result
The selected document's Phase 6.2 acquisition manifest remains `blocked`: no direct PDF asset URL on `rc.majlis.ir` was established and no original PDF was downloaded. Consequently, the real document cannot pass Phase 6.3. The committed validation report correctly records `blocked_pending_official_pdf`.

Web discovery during this phase found a 31-page FAOLEX-hosted copy and secondary reproductions, but these are not accepted as the official source and were not used as substitutes. The Parliament page URL remains the preferred source record; an HTML page is not treated as a PDF asset.

## New implementation
- `legal_bot/ingestion/official_document_validation.py`
- `tests/test_phase6_3_official_document_validation.py`
- `legal_bot/data/iran/ingestion/test_candidates/phase6_3_validation_report.json`

## Safety properties
- Fail-closed when no official PDF has been acquired.
- Rejects non-official hosts and mirrors.
- Recomputes SHA-256 from the original file.
- Validates `%PDF-` signature and opens the PDF structurally with PyMuPDF.
- Does not assert legal authenticity, current force, amendment status, or legal interpretation.
- Does not write to active legal-bank JSON files.

## Tests
- Full suite: **580 passed**.
- New Phase 6.3 tests: **5 passed**.
- `python -m compileall -q legal_bot tests`: passed.

The synthetic valid-PDF test only proves the validator's technical path. It does not constitute validation of the selected real law.

## Next action
Do not proceed to Phase 6.4 until the official PDF is acquired and its technical integrity passes. Resolve the direct PDF asset URL from the Parliament source, then rerun Phase 6.2 and Phase 6.3. No mirror fallback is permitted.
