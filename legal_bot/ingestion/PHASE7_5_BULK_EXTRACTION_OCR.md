# Phase 7.5 — Bulk text extraction and OCR

Adds bounded batch orchestration over the existing Phase 3.3–3.7 PDF pipeline.
The processor accepts an explicit acquired-document manifest only; it does not
crawl directories, access the network, or mutate original PDFs or active JSON.

## Controls
- Default accepts only manually verified `official_primary` sources.
- Secondary sources require explicit policy opt-in and still remain secondary.
- Enforces document, byte, per-source, per-document page and batch page budgets.
- Checks acquired SHA-256 when supplied; rejects non-PDF/missing files.
- OCR is opt-in (`run_ocr=True`) and remains selectively page-scoped by the existing pipeline.
- Item failures are isolated and recorded; successful output remains review-required.
- Writes one batch report atomically; no active-bank import.

## Input contract
Each `BulkPDFItem` must identify the document/source, source class, manual source
verification, `downloaded` acquisition status, local PDF path, and optionally
its expected SHA-256 and document type.

## Limitations
Tests use controlled local PDF fixtures. They do not demonstrate live access to
Parliament sources, corpus-wide OCR accuracy, or legal authenticity. OCR runtime
and language availability depend on the host Tesseract installation.
