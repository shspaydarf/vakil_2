# Phase 7.3 — Document Discovery Catalog

## Scope
This phase adds a persistent, versioned catalog for document metadata. It does not crawl websites, make network requests, download PDFs, run OCR, decide legal validity, or write to the active JSON legal bank.

## Components
- `document_catalog.py`: validated document metadata schema, stable identity, URL canonicalization, catalog persistence, duplicate grouping, filtering and audit history.
- `DocumentCatalog`: optionally binds to the Phase 7.2 `SourceRegistry`. When bound, every source must already exist; URLs must pass that source's exact host/path policy.
- Secondary and unverified source records are retained in quarantine, never promoted to official-primary by cataloging.

## Identity and deduplication
- Stable document identity is SHA-256 over `source_id` and the source's external document ID, or its canonical HTTPS URL.
- Exact content hashes create duplicate groups. Separate legal identities are retained; no records are merged.
- Re-import of identical metadata is skipped. Different metadata under the same stable identity is rejected and audited as a conflict.
- Similar titles, dates, or text are not treated as proof of duplication.

## Relationships
`related_document_ids` and `relationship_hints` are explicitly supplied metadata only. The catalog does not infer that an item amends, repeals, supersedes, or interprets another item. Any such legal relationship needs source evidence and later human review.

## Safety invariants
- Network discovery and download are disabled.
- Missing/unregistered sources are rejected when a source registry is attached.
- Secondary/unverified sources are quarantined.
- Registry URL policy is enforced for supplied URLs.
- Catalog writes are atomic and versioned; stale expected versions fail.
- Every ingest operation and rejected record is auditable.
- Active legal bank is never modified.

## Limitations
A catalog entry is an inventory candidate, not proof of authenticity, currency, enforceability, completeness, or legal effect. Real-world bulk discovery and source reachability remain untested and belong to later phases under explicit access policy.
