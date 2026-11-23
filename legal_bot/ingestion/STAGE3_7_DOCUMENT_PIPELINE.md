# Phase 3.7 — Controlled document pipeline

`process_pdf_document(pdf_path, output_dir, ...)` connects the Phase 3.3–3.6
components in this order: text extraction, selective OCR, legal structure
parsing, and typography normalization. It emits separate stage sidecars, a
consolidated `05_staging_document.json`, and a SHA-256 artifact manifest.

## Safety boundaries

- The input PDF is read-only; its SHA-256 is checked across extraction/OCR.
- OCR runs only for pages marked sparse by the extractor, unless disabled.
- Non-empty OCR replaces text only on its selected page. Empty OCR never
  deletes previously extracted text.
- Every page retains page number, extraction text, chosen text, and provenance.
- The parser and OCR outputs remain review-required machine-generated data.
- No active legal JSON bank, source connector, or download queue is modified.
- This is a staging pipeline, not a legal validation or automatic import tool.

## Output files

1. `01_extraction.json`
2. `02_ocr.json` (only when OCR was needed and enabled)
3. `03_legal_structure.json`
4. `04_normalized_text.json`
5. `05_staging_document.json`
6. `manifest.json` with source and artifact hashes

## Example

```python
from legal_bot.ingestion.document_pipeline import process_pdf_document

result = process_pdf_document("incoming/law.pdf", "staging/law-001")
print(result.to_dict())
```

OCR requires Tesseract plus the `fas` and `eng` trained data. If a scanned page
needs OCR and the runtime dependencies/language packs are missing, processing
fails closed rather than silently claiming a complete package. Set
`run_ocr=False` only when intentionally creating a partial package; its
manifest explicitly marks OCR as skipped.
