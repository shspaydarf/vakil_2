# Stage 4.5 — Cross-source matching

## Purpose

Compare a staged document (including its extracted metadata/text) with source-page
records already obtained by MACHINA's discovery connectors. This is an offline
comparison layer; it does not crawl URLs, download source PDFs, or certify legal
validity.

## Module

`legal_bot.ingestion.official_source_matcher`

Public functions:

- `match_document_against_sources(document, source_records, source_catalog=None, ...)`
- `write_source_match_report(report, output_path)`

`source_records` accepts dictionaries shaped like `CandidateDocument.to_dict()`
with optional `metadata` and `normalized_text`/`text` fields. The source catalog
is the existing `legal_bot/ingestion/SOURCE_CATALOG_V1.json` structure.

## Matching behavior

- Normalizes Persian/Arabic letter variants, Persian/Arabic digits, and whitespace.
- Compares title, document type, issuer, number, approval date, and publication date.
- Compares full text and emits exact, near-exact, partial, or material-difference
  candidates, with SHA-256 fingerprints.
- Uses the source catalog's `source_role`; `secondary_discovery` (including
  Ekhtebar) is never treated as official confirmation.
- A match against a preferred official-source role is reported only as
  `official_source_match_candidate`, not as verified authenticity.
- Metadata conflicts and text differences become review findings.

## Deliberate safety boundaries

- `official_confirmation` is always `false` in this stage.
- `live_source_access_performed`, `legal_validity_proven`, and
  `active_bank_changed` are always `false`.
- No URL is fetched and no external site is contacted.
- No active law JSON, source catalog, original PDF, or staging record is changed.
- Text similarity is a screening signal, not proof of amendment, repeal, or legal
  effect. Official source evidence and human legal review remain necessary.

## Output

The JSON report contains per-source identity-field matches/conflicts, source role,
page URL/host, text similarity and comparison class, SHA-256 values, findings,
and explicit non-proof flags. Write it to a separate staging/report path.

## Tests

`tests/test_official_source_matcher.py` covers official-role candidate matching,
secondary-source limitations, metadata/text conflicts, missing source records,
threshold validation, and atomic report writing.
