# MACHINA Legal Engine — Phase 5.1 Report

**Phase:** 5.1 — Safe JSON Bank Architecture & Read-only Audit  
**Base:** Phase 4.7 Integration Orchestrator (2026-11-01)  
**Result:** PASS — architecture deliverable and read-only inventory completed.

## What changed
- Added `legal_bot/ingestion/bank_architecture.py` with `inspect_bank()`.
- Added `legal_bot/ingestion/STAGE5_1_BANK_ARCHITECTURE.md` documenting current schemas, consumer compatibility, candidate envelope, future transaction protocol and fail-closed rules.
- Added `tests/test_bank_architecture.py` with read-only, invalid/missing JSON and real-bank checks.
- No existing data file, active JSON bank, consumer, downloader policy, or network setting was changed.

## Read-only inventory of active corpus files
The inventory was generated from the extracted Phase 4.7 base. SHA-256 values below identify the exact byte content inspected.

| File | JSON status | Record/list entries | Size | SHA-256 |
|---|---:|---:|---:|---|
| `laws.json` | Valid | 8,409 | 6,492,268 B | `d21b1c56a575511973836271a54d98286a06aff07e93e7852abd0cd1f3f4e7f6` |
| `rulings.json` | Valid | 286 | 428,432 B | `2ff2845a9d8f9da61abb1d695684335e8fb68bdd52783ebbde1148225bbc3236` |
| `consultations.json` | Valid | 179 | 256,803 B | `30bcac47ebeb98a7c8f14b3c35cbb16ce50454ed3853ca92eb47ff4ee827a7a9` |
| `samples_and_circulars.json` | Valid | 98 | 92,425 B | `2b042cacf719e2148acf27f317e8233fc0950b4fb99754cccc9bef236b2ba748` |

**Counting note:** `laws.json` count is the total number of elements across all title-keyed lists. It includes metadata/special rows such as `_meta`; it is not a count of validated legal articles. Rulings count combines Supreme Court and Administrative Justice Court lists. Samples/circulars combines both lists.

Reference/control files found: `official_sources.json`, `secondary_academic_sources.json`, `law_catalog.json`, `quarantine_manifest.json`, and `quarantine/inactive_laws.json`.

## Architectural findings
1. The active bank is not one homogeneous schema. Laws are title-keyed lists; rulings, consultations, and samples/circulars use distinct envelopes and must remain separate.
2. `legal_bot/laws.py` consumes `laws.json`, `rulings.json`, and `consultations.json`; search indexes are built at runtime and include additional filters. A future import must preserve these existing shapes or introduce a separately tested adapter.
3. Law list entries are not uniformly article records: `_meta` entries exist. A future importer must distinguish metadata from article records before assigning IDs or deduplicating.
4. Consultations and rulings are separate legal-information classes. Templates/circulars are operational/educational material, not statutes.
5. Source catalogs and quarantine controls are reference/control data, not automatic import destinations.

## Safety guarantees
- `inspect_bank()` only reads files and computes hashes/shapes/counts.
- No staging, quarantine, or archive directories are created by this phase.
- No write path to active bank exists in this module.
- No network access, download, OCR, source promotion, or legal-status determination is performed.
- Technical validity is not legal authenticity, enforceability, or currentness.

## Tests
- New focused tests: **3 passed**.
- Full project suite: **537 passed in 15.24s**, zero failures.
- The focused tests verify file hashes remain unchanged after inspection, invalid/missing JSON is reported without repair, and all four actual active target files parse.

## Next phase
Phase 5.2 should implement isolated staging/quarantine package creation and strict candidate/record schema validation. It must still be dry-run only and must not write to the active bank. Transactional import, snapshot, atomic replacement and rollback should be a later independently reviewed phase.
