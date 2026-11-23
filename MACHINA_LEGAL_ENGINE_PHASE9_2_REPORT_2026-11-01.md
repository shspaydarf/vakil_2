# MACHINA Legal Engine — Phase 9.2 Report

## Scope
Connected the Phase 9.1 source-routing policy to the existing secure PDF downloader for a single, explicitly observed direct-PDF URL. This is a controlled bridge, not a live source connector.

## Changes
- Added `legal_bot/ingestion/phase9_2_acquisition_bridge.py`.
- Added `tests/test_phase9_2_acquisition_bridge.py` (6 tests).
- Downloads, when explicitly enabled and supplied with a verified direct PDF URL, are restricted to `phase9_2_quarantine` under the staging root.
- The existing secure downloader continues to enforce HTTPS/host allowlisting, public DNS checks, TLS verification, redirect limits, response/content-type/size limits, PDF signature/EOF checks, and PyMuPDF validation.
- Majles results remain pending human review. Ekhtebar results are explicitly secondary and quarantine-only.
- No HTML scraping, browser automation, print workflow, OCR, legal-validity assessment, or active-bank import was added.

## Verification
- Baseline before changes: 701 tests passed.
- Phase 9.2 focused tests: 6 passed.
- Full suite after changes: **707 passed in 29.20s**.
- `python -m compileall -q legal_bot tests`: passed.
- Four active legal JSON bank hashes remain identical to the Phase 7.1 values:
  - `laws.json`: `d21b1c56a575511973836271a54d98286a06aff07e93e7852abd1cd1f3f4e7f6`
  - `rulings.json`: `2ff2845a9d8f9da61abb1d695684335e8fb68bdd52783ebbde1148225bbc3236`
  - `consultations.json`: `30bcac47ebeb98a7c8f14b3c35cbb16ce50454ed3853ca92eb47ff4ee827a7a9`
  - `samples_and_circulars.json`: `2b042cacf719e2148acf27f317e8233fc0950b4fb99754cccc9bef236b2ba748`

## Live-operation limitation
No live network download was attempted in this phase. The earlier runtime DNS failure remains unresolved, and no independently verified direct PDF asset URL was supplied for the selected test case. Therefore this phase proves the routing-to-downloader bridge with controlled tests, **not** successful live acquisition.

## Safety
No active legal JSON bank, production setting, or existing source document was modified. The downloader remains opt-in; a missing direct PDF URL or missing downloader blocks acquisition. All accepted files require human review.

## Next
Phase 9 is complete within its agreed two-message scope. The next planned work is Phase 10 final QA/readiness, kept concise; live connectivity should only be claimed after an actual runtime download succeeds.
