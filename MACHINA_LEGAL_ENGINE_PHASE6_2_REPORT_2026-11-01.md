# MACHINA Legal Engine — Phase 6.2 Report

## Decision: acquisition blocked safely

The Phase 6.2 acquisition workflow and live access check were completed. **The official PDF was not acquired.** This is a blocked acquisition outcome, not a successful download.

Selected candidate: `MACHINA-PHASE6-1-IR-LAW-001`  
Document: «قانون احکام دائمی برنامه های توسعه کشور»  
Official page: `https://rc.majlis.ir/fa/law/print_version/1014070`

## Live access evidence
- The official page retrieval through the web access layer timed out.
- A direct network request from the execution environment could not resolve `rc.majlis.ir` (DNS resolution failure).
- The selected URL is a page URL, not a verified direct PDF asset URL.
- No official direct PDF asset URL could be confirmed.

## Safety behavior
- The FAOLEX copy was **not** used as a substitute or fallback.
- The downloader was not pointed at the HTML page URL as if it were a PDF.
- No PDF bytes were acquired; therefore no SHA-256, byte size, page count, or download timestamp is claimed.
- No OCR, extraction, parsing, staging, final validation, or import was run.
- Active bank files were not modified.

## Implementation delivered
`legal_bot/ingestion/official_pdf_acquisition.py` adds a fail-closed acquisition entry point. It requires an explicitly supplied direct HTTPS PDF asset URL on the exact allowlisted official host `rc.majlis.ir`, then delegates to the existing `SecurePDFDownloader`. It atomically writes an acquisition manifest even when blocked. It never substitutes mirrors.

Manifest: `legal_bot/data/iran/ingestion/test_candidates/phase6_2_acquisition_manifest.json`  
Status: `blocked`  
Reason: `official_pdf_asset_url_unresolved`

## Active-bank integrity fingerprints
The following active JSON files were fingerprinted after the phase work; no code path in this phase writes to them:

| File | SHA-256 |
|---|---|
| `laws.json` | `d21b1c56a575511973836271a54d98286a06aff07e93e7852abd0cd1f3f4e7f6` |
| `rulings.json` | `2ff2845a9d8f9da61abb1d695684335e8fb68bdd52783ebbde1148225bbc3236` |
| `consultations.json` | `30bcac47ebeb98a7c8f14b3c35cbb16ce50454ed3853ca92eb47ff4ee827a7a9` |
| `samples_and_circulars.json` | `2b042cacf719e2148acf27f317e8233fc0950b4fb99754cccc9bef236b2ba748` |
| `law_catalog.json` | `ce7720c8ea122736d4c349e431964ba284d4b9ec7c3f86d05cb700075c97a737` |
| `official_sources.json` | `ef4119d629f80d4e37e8fda858ebd37a6afd1aaba476742661b50e73a5e640f5` |

## Tests
- New Phase 6.2 tests: 5 passed.
- Full project suite: **575 passed**, 0 failed.
- `python -m compileall -q legal_bot tests`: passed.
- ZIP integrity check: passed.

## Next action
Retry the official page from an environment with working DNS/network access, discover the direct PDF asset URL on `rc.majlis.ir`, and rerun acquisition with downloads explicitly enabled. If the official source remains unavailable, keep the candidate blocked. Do not use FAOLEX or another mirror for ingestion.
