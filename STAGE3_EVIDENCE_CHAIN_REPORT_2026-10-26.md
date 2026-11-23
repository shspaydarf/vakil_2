# LegalBot Stage 3 — Evidence Chain & Timeline Filters

Date: 2026-10-26

## Scope

This patch builds on the Stage 2 document-extraction baseline and hardens the source-linked chronology and claim/evidence matrix. It does not make legal findings or determine authenticity, admissibility, credibility, or legal sufficiency.

## Changes delivered

- Added API query filters for timeline event `status` and `type`, while preserving the `undated` option.
- Added validation for unsupported timeline filter values.
- Added `filters` and `filtered_counts` metadata so clients can distinguish filtered result counts from whole-case chronology counts.
- Added explicit `origin_source` provenance to each evidence claim: document ID/name, page, original signal text, and signal stance.
- Tightened independent-source counting: a different page in the same document is not treated as an independent source. Independent corroboration requires a distinct document record, non-copy text, and a relevant source span.
- Corrected filtered Evidence count summaries to reflect the returned claims and matrix.
- Added Mini App controls for filtering timeline by status/type and Evidence by claim status.
- Timeline UI can display multiple source references for merged events; Evidence UI explicitly separates the originating claim source from candidate supporting/contrary source spans and shows source offsets when available.
- Strengthened language in the UI to explain that machine-generated statuses are review leads, not judicial findings.

## Validation

- `pytest -q`: **61 passed**
- `python preflight.py`: **PASS**
- `python -m compileall -q legal_bot`: **PASS**
- `node --check miniapp/app.js`: **PASS**

## Limits / next steps

- Evidence matching remains deterministic lexical matching, not semantic entailment. A text match may be irrelevant or may misread negation/context; all material links require human review.
- A distinct file record is only a provenance boundary, not proof of independence, authenticity, or truth. Duplicated documents can still exist as separate records.
- Source offsets refer to extracted text, not necessarily stable PDF coordinates. Page markers may be absent or imperfect when extraction/OCR does not preserve them.
- Review decisions are not yet persisted as an auditable lawyer-confirmed evidence graph. Before using these outputs as canonical facts, implement reviewed/rejected link decisions, actor/time, source versioning, and an immutable audit trail.
- OCR quality and API behavior have not been tested against a live Telegram deployment or a representative corpus of scanned Persian legal documents.
