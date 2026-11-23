# LegalBot Stage 2 — Regression & Hardening Audit

Date: 2026-10-06

## Result

Stage 1 Case Management + Stage 2 Documents were regression-tested together.

- Full pytest suite: **31 passed**
- Preflight: **PASS**
- Python compile: **PASS**
- Mini App JavaScript syntax: **PASS**
- HTTP case + document smoke: **PASS**
- Clean import smoke: **PASS**

## Fixes made during audit

1. Restored the required `persian_case_search.py` runtime dependency to the distributable root. Stage 2 packaging had accidentally omitted it.
2. Added the dependency to preflight required-file checks.
3. Made Mini App multi-file document ingestion atomic. A failed file no longer leaves a partial batch or consumes an addition slot.
4. Added regression coverage for failed mixed document batches.
5. Fixed isolated entitlement/credit tests so their temporary DB path is actually applied rather than relying on test ordering.
6. Removed runtime `legal_bot.db` and uploaded storage artifacts from the distributable package.

## Architecture check

The Mini App remains an adapter:

`Mini App → HTTP API → Core Services → Repository/DB/Storage`

No duplicate legal/business rules were introduced in the Mini App.
