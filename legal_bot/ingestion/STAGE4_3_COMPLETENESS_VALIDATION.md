# Phase 4.3 — Document completeness screening

## Purpose

This phase adds a conservative screening step for possible missing pages,
missing or repeated article numbers, repeated numbered notes, blank extracted
pages, low reported OCR confidence, page-count mismatches, and structural page
references outside the observed page range.

## API

- `validate_document_completeness(pages, structure, expected_page_count=..., source_sha256=...)`
- `validate_staging_document(staging_document)` accepts the Phase 3.7
  `05_staging_document.json` payload directly.
- `write_completeness_report(report, output_path)` writes an atomic JSON sidecar.

Example:

```python
import json
from legal_bot.ingestion.completeness_validator import (
    validate_staging_document, write_completeness_report,
)

with open("05_staging_document.json", encoding="utf-8") as stream:
    staging = json.load(stream)
report = validate_staging_document(staging)
write_completeness_report(report, "06_completeness_report.json")
```

## Safety and interpretation

- This is a screening tool, not proof that a legal instrument is complete.
- An article-number gap can be intentional (for example, a repealed article).
- A blank page can be intentional or may contain image-only content.
- Low OCR confidence is a review signal, not a declaration that text is wrong.
- The validator never repairs text, alters the source PDF, changes queue state,
  or writes to the active legal JSON bank.
- Every report remains `review_required=true` and
  `completeness_proven=false`, even when no anomaly is detected.

## Test coverage

Seven focused tests cover clean screening, page sequence anomalies, blank
pages, article-number gaps, duplicate articles/notes, OCR confidence and page
count mismatch, and JSON report serialization.
