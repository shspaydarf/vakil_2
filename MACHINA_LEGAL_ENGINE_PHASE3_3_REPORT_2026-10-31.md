# MACHINA Legal Engine — Phase 3.3: PDF text extraction

**Status:** implemented; automated tests passed.  
**Base:** Phase 3.2 secure PDF acquisition ZIP.  
**Scope:** extract text from text-based PDFs and identify pages that likely require OCR in Phase 3.4.

## Delivered

- `legal_bot/ingestion/pdf_text_extractor.py`
  - Extracts each page independently using PyMuPDF.
  - Preserves 1-based page numbers, text blocks and their bounding boxes.
  - Produces page-level character counts and image-block counts.
  - Uses configurable thresholds to flag sparse/scanned pages for OCR.
  - Supports optional SHA-256 verification against acquisition metadata.
  - Enforces page-count limits and rejects missing, encrypted, or unreadable PDFs.
  - Writes a separate JSON sidecar atomically; does not modify the source PDF.
- `tests/test_pdf_text_extractor.py`: 7 focused tests.
- `legal_bot/ingestion/STAGE3_3_PDF_TEXT_EXTRACTION.md`: operating notes and boundaries.

## Quality classification

The default screening threshold is 40 extracted characters per page and at least 60% text-bearing pages. This is a routing heuristic, not a legal-completeness guarantee. The output explicitly flags pages below the threshold. Mixed documents can therefore send only sparse page numbers to the later OCR stage.

## Safety and boundaries

- No network access or source download is performed by this stage.
- The original PDF remains byte-for-byte unchanged.
- Extracted text is a separate staging artifact and is not inserted into the active JSON law bank.
- OCR, legal structure recognition, validation, and activation remain later phases.
- PyMuPDF text extraction may not perfectly preserve columns, tables, footnotes, or complex Persian typography; quality review is still required.

## Verification

- Focused extractor + secure-fetcher tests: **13 passed**.
- Full discovered unittest suite (`tests/test*.py`): **27 passed, 0 failed**.
- Tests use locally generated PDFs; no live source documents were downloaded or validated in this phase.
