# Phase 6.3 — Official document validation

Call `validate_official_pdf_evidence(acquisition_manifest, output_path=...)` after Phase 6.2. The validator accepts only a downloaded PDF whose final source URL is HTTPS on `rc.majlis.ir` and ends in `.pdf`. It verifies local file presence, signature, SHA-256, PyMuPDF structural readability and optional page count.

A successful result means **technical integrity passed pending human legal review**. It never certifies authenticity, current legal force, amendment/repeal status, or legal interpretation. A blocked Phase 6.2 manifest remains blocked. No mirror fallback is accepted.
