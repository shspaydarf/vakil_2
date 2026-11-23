# Phase 5.1 — Safe JSON Bank Architecture

## Scope
This phase is an architecture and read-only inventory step. It does not alter any active JSON, change search consumers, import records, or enable network access.

## Current active corpus files
- `legal_bot/data/iran/laws.json`: object keyed by Persian law title; each value is a list of article-like objects. The current consumer is `legal_bot/laws.py` and its `RAW`/`INDEX` construction. Some groups contain `_meta` rows, and the consumer applies its own conservative filters/quarantine list. A future importer must not assume every list element is a legal article.
- `rulings.json`: object with separate `rulings` and `diwan_adalat_rulings` lists; consumed into `RULING_INDEX`.
- `consultations.json`: object with `metadata` and `consultations`; consumed into `CONSULTATION_INDEX`.
- `samples_and_circulars.json`: object with `metadata`, `samples`, and `circulars`; these are practical templates/administrative guidance, not statutes.

## Reference/control files (not direct import targets)
`official_sources.json`, `secondary_academic_sources.json`, `law_catalog.json`, `quarantine_manifest.json`, and `quarantine/inactive_laws.json` have distinct roles. In particular, a secondary academic reference is not an official legal source; quarantine records must not be exposed to active search.

## Proposed storage layout for Phase 5.2+
- `legal_bot/data/iran/ingestion/staging/<batch_id>/`: immutable candidate package and validation reports.
- `legal_bot/data/iran/ingestion/quarantine/<batch_id>/`: blocked or unresolved candidate packages.
- `legal_bot/data/iran/ingestion/archive/<batch_id>/`: retained imported package, manifest, and prior-version lineage.
- Active files remain at their existing paths for backward compatibility.

## Required candidate envelope (design only)
Each candidate should carry: `candidate_id`, `document_kind`, `title`, `jurisdiction`, `source_authority_id`, `source_url`, `source_document_sha256`, `acquired_at`, `original_pdf_path`, `extraction_pipeline_version`, `extracted_text_sha256`, `records`, `validation_report_refs`, `review_decision`, and `supersedes` (optional). The original PDF is immutable evidence; extracted text is derivative and must retain page references.

Each record should carry a stable `record_id`, `record_kind`, `parent_document_id`, `locator` (article/paragraph/ruling number), `text_original`, optional `text_normalized`, `source_page_refs`, and `record_sha256`. Record-level provenance is mandatory.

## Import transaction (future phase)
1. Dry-run only: validate envelope, file hashes, document/record schemas, IDs, duplicates, provenance and final-gate report.
2. Human review: explicit reviewer ID, timestamp and decision; no implicit approval from technical tests.
3. Prepare: create a full byte-for-byte snapshot of every target file and record its checksum.
4. Build candidate output in a separate temporary directory; never mutate live JSON in place.
5. Validate consumer compatibility and all target checksums; fsync prepared files.
6. Atomic replace one target at a time only under a transaction lock, with a journal that records each completed replacement.
7. On any failure, restore all already-replaced targets from verified snapshots; record rollback outcome.
8. Retain old/new hashes, batch ID, reviewer decision and rollback data in an append-only audit record.

## Fail-closed rules
- No import without explicit human approval.
- No active write when provenance is missing, official-source match is absent where required, hashes mismatch, or validation is blocked.
- No direct overwrite of active files during staging or validation.
- No merging of different document kinds into the same collection.
- No promotion of samples, circulars, consultations or academic references into statutes.
- No claim of legal validity/currentness based solely on successful technical validation.

## Phase 5.1 deliverable
`bank_architecture.py` exposes `inspect_bank()` as a read-only inventory. It fingerprints the four active corpus files and reports the control/reference files. It deliberately does not create staging folders or write reports, keeping this phase side-effect-free.
