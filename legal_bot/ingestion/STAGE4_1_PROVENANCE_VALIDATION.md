# Phase 4.1 — Source provenance screening

## Scope

Adds a fail-closed, sidecar-only screen for the origin and acquisition trail of
candidate legal documents. It cross-checks the source ID against
`SOURCE_CATALOG_V1.json`, checks page/asset/download URL hosts against the
configured exact-host allowlist, validates the recorded SHA-256, optionally
re-hashes the local PDF and optionally links the Phase 3.7 pipeline manifest.
It also flags disagreements in title/issuer/document number/date when both
candidate and download manifest contain those values.

## Important limitation

A matching domain, HTTPS acquisition record and SHA-256 prove consistency of
the recorded chain and file identity, not the legal authenticity, signature,
publication status, current validity or completeness of an instrument. This
module therefore always returns `document_authenticity: not_proven`. A report
may only mark `eligible_for_next_review`; it does not approve activation or
write to the active legal JSON bank.

## API

`validate_document_provenance(candidate, download_manifest, source_catalog=None,
 pipeline_manifest=None, pdf_path=None)` returns a `ProvenanceReport`.
`write_provenance_report(report, path)` writes an atomic JSON sidecar.

The source catalog remains read-only. No network access, signature bypass,
source scraping, queue mutation or active-corpus import is performed.

## Validation

The tests use local fixture bytes and the configured source catalog. They cover
consistent source/hash records, unknown source IDs, unlisted hosts, local PDF
hash mismatch, pipeline hash mismatch and sidecar writing. They do not assert
that any real-world law or source publication is authentic.
