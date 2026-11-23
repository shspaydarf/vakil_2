# MACHINA Legal Engine — Phase 3.7 Report

Date: 2026-11-01
Base: `MACHINA_Legal_Engine_Phase3_6_Legal_Text_Normalization_2026-10-31.zip`

## Delivered

- Added `legal_bot/ingestion/document_pipeline.py` as the controlled orchestration layer for phases 3.3–3.6.
- Added `legal_bot/ingestion/STAGE3_7_DOCUMENT_PIPELINE.md` with API, output contract, safety boundaries, and runtime requirements.
- Added `tests/test_document_pipeline.py` with four focused integration tests.

## Pipeline behavior

1. Verify input file and calculate SHA-256.
2. Extract page-preserving PDF text using Phase 3.3.
3. OCR only sparse pages identified by the extractor, when enabled.
4. Merge OCR page text without replacing a page with an empty OCR result; preserve original extraction text and provenance.
5. Parse legal structure using Phase 3.5.
6. Normalize typography using Phase 3.6 while retaining raw text.
7. Write separate sidecars, a consolidated staging document, and a manifest containing SHA-256 hashes for each artifact.

## Safety boundaries

- The source PDF is read-only and checked by SHA-256.
- OCR/structure results remain machine-generated and review-required.
- The pipeline does not alter the download queue, source registry, or active legal JSON bank.
- The output is a staging package, not legal validation and not an import authorization.
- If OCR is required but dependencies/language data are missing, the run fails rather than silently claiming completion. `run_ocr=False` is an explicit partial-run option and is labeled as skipped.

## Verification

- Focused pipeline tests: **4 passed**.
- Full discovered unittest suite: **49 passed, 0 failed**.
- Python compilation of new module and tests: passed.
- Integration coverage includes text-only PDF path, selective OCR merge (mocked OCR engine), empty OCR non-destructive behavior, missing-file fail-closed behavior, manifest generation, and source-PDF immutability.

## Not yet verified

- No live PDF was downloaded from Majles or Ekhtebar in this phase.
- The pipeline's OCR integration was tested with a deterministic mocked OCR result; the underlying Tesseract execution belongs to Phase 3.4 and is not re-benchmarked here.
- No legal accuracy benchmark has been run against a corpus of real Iranian statutes.
- No document is automatically promoted to the active law bank.
