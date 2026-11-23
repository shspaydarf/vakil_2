# Stage 6 Release Audit — Drafting

Date: 2026-10-06

## Scope
Regression and release audit of the Stage 6 Drafting build, covering Stage 1–6 integration, drafting artifacts, API contracts, ownership, archived-case behavior, versioning, packaging, and syntax/preflight checks.

## Results
- Pytest: **43 passed**
- Preflight: **PASS**
- Python compile: **PASS**
- Mini App JavaScript syntax: **PASS**
- Clean-package runtime/cache audit: **PASS**

## Bugs fixed during audit

### 1. Archived cases could enter Drafting
The unified drafting workflow previously checked case existence but did not reject archived cases. This was inconsistent with the AI workflow and allowed a direct Draft request against an archived case.

Fix: archived cases now return `CASE_ARCHIVED` before drafting and cannot create artifacts.

### 2. Draft artifact creation on archived cases
The persistence layer independently accepted an owned archived case.

Fix: `save_draft_artifact()` now rejects archived cases with `case_archived`.

### 3. Concurrent artifact version allocation
Version numbers were allocated using `MAX(version_no)+1` without serializing the allocation transaction.

Fix: artifact version allocation now uses `BEGIN IMMEDIATE`, preventing concurrent requests from calculating the same next version number.

## Architecture check
No business rules were moved into the Mini App. The flow remains:

`Mini App → HTTP API → ProductCaseService / Drafting Workflow → Core Engines → DB / Storage`

Draft artifacts remain immutable records with case/user ownership and explicit human-review status.

## Packaging
The release artifact was cleaned of generated Python bytecode, pytest cache, database files, and runtime storage state.

## Release status
**STAGE 6 IS RELEASE-AUDITED AND READY TO USE AS THE BASELINE FOR STAGE 7.**
