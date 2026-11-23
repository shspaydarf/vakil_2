# Phase 4.2 — Legal document identity metadata screening

## Scope
Adds a conservative, deterministic screening module for document type, title,
issuing authority, document number, enactment/notification/publication dates,
source-to-extracted metadata agreement, and coarse issuer/type compatibility.

## Module
`legal_bot/ingestion/document_metadata_validator.py`

Public API:
`validate_document_metadata(candidate, extracted_metadata=None, source_page_metadata=None)`

The report includes normalized display values, per-field checks, structured
findings, an overall screening status, and `legal_authenticity: not_proven`.

## Safety boundaries
- No missing title, issuer, number, or date is inferred or fabricated.
- Conflicting values are surfaced, not silently overwritten by source priority.
- Date parsing accepts unambiguous YYYY-MM-DD, YYYY/MM/DD, and YYYY.MM.DD.
  Years 1200–1499 are treated as likely Solar Hijri and checked conservatively
  by month/day ranges only; this is not full Jalali leap-year validation.
- Authority/type compatibility is a coarse review hint, not a legal opinion
  about competence or validity.
- The module does not modify PDFs, manifests, the download queue, or active law JSON.
- A passed screen never means the instrument is authentic, current, or in force.

## Tests
Run from repository root:
`python -m unittest tests.test_document_metadata_validator tests.test_provenance_validator`
