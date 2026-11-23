# MACHINA Legal Engine — Phase 9.1 Report

## Scope
Implemented a small, conservative acquisition-routing policy. This phase does not implement a live connector or perform network operations.

## Changes
- Added `legal_bot/ingestion/phase9_1_acquisition_policy.py`.
- Added `tests/test_phase9_1_acquisition_policy.py` (6 tests).
- Official Majles route defaults to an HTML-capture candidate unless a direct official PDF is independently observed.
- The multi-step Majles print workflow remains deferred; no browser automation was added.
- Ekhtebar is always classified as secondary. Its PDFs are quarantine-only and cannot be promoted to official-primary material by this policy.
- HTTPS and exact host allowlisting are enforced; unknown source IDs and hosts are rejected.
- Plan integrity is protected by SHA-256 and validation checks.

## Verification
- Baseline from Phase 8.3: 695 tests passed (full verbose run, 30.01s).
- New Phase 9.1 tests: 6 passed.
- Full suite after changes: **701 passed in 28.02s**.
- `python -m compileall -q legal_bot tests`: passed.
- Four active legal JSON bank hashes match the Phase 7.1 recorded hashes.
- ZIP integrity checked separately after packaging.

## Explicit limitations
- No live request, download, HTML capture, PDF generation, OCR, staging write, or legal validation was performed.
- The earlier Phase 8.3 DNS failure remains unresolved; this phase does not claim runtime connectivity.
- No active legal bank or production setting was modified.

## Next
Phase 9.2 should remain small: integrate this policy with the existing secure fetch/staging path and run a controlled single-file test only when runtime network access is available. Do not automate the Majles print workflow unless a simpler supported route is demonstrated.
