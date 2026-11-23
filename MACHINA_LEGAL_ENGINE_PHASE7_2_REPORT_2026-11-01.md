# MACHINA Legal Engine — Phase 7.2 Report

**Deliverable:** Versioned Source Registry

## Baseline and changes

- Starting archive: `MACHINA_Legal_Engine_Phase7_1_Bulk_Architecture_2026-11-01.zip`.
- Baseline test run before changes: **597 passed**.
- Added `legal_bot/ingestion/source_registry.py` and 10 focused tests in
  `tests/test_source_registry.py`.
- Added `legal_bot/ingestion/PHASE7_2_SOURCE_REGISTRY.md`.

## Implemented

- Typed source records with authority level, publisher, jurisdiction, document types,
  exact allowed hosts, canonical HTTPS roots, access mode, robots policy, rate limit,
  page cap, status, access observations, and human verification evidence.
- Fail-closed defaults: unverified authority, unverified status, disabled access.
- Official-primary designation requires human review metadata and an evidence SHA-256.
- Exact-host/path URL policy; no wildcard hosts, HTTP, credentials, nonstandard ports,
  or lookalike host acceptance.
- Versioned JSON registry, append audit records, atomic writes, and optimistic version
  checks to reject stale updates.
- Explicit policy summary for stopping on 403/429/CAPTCHA; no challenge bypass.

## Safety boundary

No network calls, discovery, downloads, OCR, staging, or active-bank mutation were
performed. No Majles or Ekhtebar source has been newly certified or marked reachable.
A successful URL-policy check is not proof of legal authenticity or validity.

## Validation

The final test, compile, and archive-integrity results are recorded in the delivery
message. Existing bank JSON files are preserved; the registry is a separate new file
format and is not wired to automatic activation.

## Final verification (2026-11-01)

- Full suite: **607 passed** (baseline 597; 10 new tests).
- `python -m compileall -q legal_bot tests`: passed.
- Core legal-bank SHA-256 values match the Phase 7.1 baseline exactly:
  - `laws.json`: `d21b1c56a575511973836271a54d98286a06aff07e93e7852abd0cd1f3f4e7f6`
  - `rulings.json`: `2ff2845a9d8f9da61abb1d695684335e8fb68bdd52783ebbde1148225bbc3236`
  - `consultations.json`: `30bcac47ebeb98a7c8f14b3c35cbb16ce50454ed3853ca92eb47ff4ee827a7a9`
  - `samples_and_circulars.json`: `2b042cacf719e2148acf27f317e8233fc0950b4fb99754cccc9bef236b2ba748`
