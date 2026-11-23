# MACHINA Legal Engine — Phase 4.4 Report

Implemented conservative duplicate and version-difference screening in
`legal_bot/ingestion/version_conflict_validator.py`.

## Delivered
- Detects exact-text duplicate candidates using normalized text fingerprints.
- Detects same-identity documents with different text as possible version pairs.
- Detects configurable near-duplicate text candidates.
- Reports article numbers present only in either document and changed article text.
- Stores SHA-256 text fingerprints, source document identifiers, date labels, and pairwise similarity.
- Writes a standalone JSON report atomically.
- Keeps legal effect explicitly undetermined; no auto-merge, overwrite, promotion,
  or active-law-bank mutation is performed.

## Validation
- New focused tests: 6 passed.
- Full pytest suite: 515 passed.
- `compileall` for new module and tests: passed.

Tests use synthetic fixtures. No live corpus of Iranian laws was used, so
similarity thresholds and metadata matching still require calibration against
real Majlis and Ekhtebar documents.
