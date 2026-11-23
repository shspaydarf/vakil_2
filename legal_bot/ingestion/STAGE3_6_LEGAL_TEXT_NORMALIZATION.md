# Stage 3.6 — Legal text normalization

## Scope
Adds a conservative, deterministic normalization layer for page text produced by PDF extraction (3.3) or Persian OCR (3.4), optionally including the structured sidecar from 3.5.

## Behavior
- Retains each page's original `raw_text` verbatim and emits `normalized_text` separately.
- Canonicalizes Arabic/Persian yeh and kaf variants and heh variants.
- Converts ASCII and Arabic-Indic digits to Persian digits by default; callers may disable this policy.
- Normalizes whitespace and duplicate ZWNJ while retaining meaningful ZWNJ.
- Removes invisible directional control marks that can interfere with search/display.
- Does not remove headers/footers, legal numbering, punctuation, or repeated content. Punctuation collapsing is opt-in and disabled by default.
- Preserves page number and provenance, and records raw/normalized SHA-256 hashes.
- Optionally normalizes a deep copy of parsed structure; caller's structure object is not mutated.
- Writes only a separate atomic JSON sidecar. No active legal bank integration is performed.

## API
`normalize_persian_text(text, policy=None)`
`normalize_legal_document(pages, source_sha256="", policy=None, structure=None)`
`write_normalization_json(result, output_path)`

## Limitations
The character-change indicator is a rough comparison metric, not an edit script. Normalization cannot verify OCR accuracy, legal validity, or semantic equivalence. Every result remains `review_required=True`; original text and source PDF must remain available for audit.
