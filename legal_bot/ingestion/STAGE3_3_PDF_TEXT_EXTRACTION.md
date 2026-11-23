# Stage 3.3 — PDF text extraction

Use `extract_pdf_text(pdf_path, expected_sha256=...)` from `legal_bot.ingestion.pdf_text_extractor` after a PDF has passed the secure acquisition stage. The optional hash should be copied from the acquisition manifest so extraction is tied to the exact acquired bytes.

The returned object contains document metadata, one entry per page, ordered text blocks with bounding boxes, character counts, and a quality/routing decision. `scan_or_ocr_page_numbers` is a 1-based list of pages whose extracted text is sparse. `needs_ocr` is a document-level signal; mixed PDFs may contain both extractable text pages and sparse pages.

Persist the result with `write_extraction_json(result, output_path)`. The JSON is a sidecar artifact; neither the source PDF nor the active law JSON bank is modified.

Thresholds are configurable with `ExtractionPolicy`. Defaults (40 characters/page; 60% text-bearing pages) are conservative screening heuristics and must be calibrated against representative Persian legal PDFs. Do not interpret `text_extractable` as proof that all legal content, tables, footnotes, or page layout were captured correctly.

OCR is deliberately out of scope and belongs to Stage 3.4. No network requests are made by this module.
