# Stage 4.4 — Duplicate and version-difference screening

`version_conflict_validator.py` compares staged legal documents for exact text
matches, same-identity/different-text candidates, and configurable near-duplicate
text similarity. Where article structures are supplied, it reports article
numbers found only in either document and articles whose text differs.

## Safety boundary

The output is a screening report only. Text similarity and metadata matching do
not prove amendment, repeal, legal validity, publication, or effective dates.
No document is merged, overwritten, promoted, or imported into the active law
bank. Human review and authoritative-source comparison remain mandatory.

## Input shape

Each item may provide `document_id`/`id`, `metadata`, `normalized_text` (or
`text`), and `structure.articles` (each article has `number` and `text`). The
comparator also accepts `document_metadata`, `document_title`, `legal_structure`,
`articles`, and simple top-level metadata aliases.

## Output

`compare_legal_document_versions()` returns a `VersionConflictReport`.
`write_version_conflict_report()` writes it atomically as JSON. The report
includes pairwise relationships, text similarity, SHA-256 fingerprints,
article-level differences, and explicit undetermined legal effect.
