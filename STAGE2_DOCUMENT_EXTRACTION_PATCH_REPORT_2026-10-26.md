# LegalBot — Stage 2: Document Extraction & Review

Date: 2026-10-26

## Delivered

- Added `legal_bot/document_facts.py`, a conservative deterministic extractor for date, amount, person/party label, national-ID, and phone candidates.
- Every candidate carries its document page (when page markers exist), surrounding source snippet, approximate confidence, and explicit `needs_review` / `review_required` flags.
- Date normalization preserves the observed component order but explicitly leaves calendar system unknown; it does not convert Solar Hijri dates to Gregorian or infer legal deadlines.
- Document metadata API now includes bounded `extracted_facts` (up to 40 candidates) without exposing the complete extracted text field.
- Mini App displays the first six source-linked candidates per document with page, confidence, and a prominent human-review warning. Fixed the preview binding to use the API's actual `preview` field.
- Added a configurable PDF page cap (`MAX_DOCUMENT_PAGES`, default 250, hard cap 500), explicit encrypted-PDF rejection, image decompression size guard, and bounded `MAX_TEXT_CHARS` configuration.
- Preflight now checks the new runtime module.

## Validation

- `pytest -q`: **59 passed**
- `python preflight.py`: **PASS**
- `python -m compileall -q legal_bot`: **PASS**
- `node --check miniapp/app.js`: **PASS**

## Important limits

- Extracted values are candidates, not verified facts. Confidence is heuristic and must not be treated as calibrated probability.
- The date parser intentionally does not decide whether a date is Solar Hijri or Gregorian, nor does it calculate a legal deadline.
- This patch presents candidates for review but does not yet persist user corrections as an audited fact record. That should be added before downstream evidence analysis treats these candidates as canonical facts.
- OCR quality depends on the installed Tesseract binary and Persian language data. The test suite validates control flow and metadata, not OCR accuracy across a representative corpus of scanned Persian court documents.
- No live Telegram deployment or production-host test was run.
