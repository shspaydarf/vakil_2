# MACHINA Legal Engine — Phase 3.6 Report

Implemented conservative Persian legal-text normalization on top of the Phase 3.5 ZIP.

Added:
- `legal_bot/ingestion/legal_text_normalizer.py`
- `tests/test_legal_text_normalizer.py`
- `legal_bot/ingestion/STAGE3_6_LEGAL_TEXT_NORMALIZATION.md`

The module preserves raw page text, emits normalized text, hashes both versions, retains page/provenance metadata, and can normalize a copied 3.5 structure sidecar. It writes only a staging JSON sidecar and does not modify the active law bank.

Validation: 7 focused normalization tests passed; the complete discovered suite passed 45/45 tests. Both new Python files passed bytecode compilation. Tests used controlled fixtures; no real-world corpus accuracy claim is made.
