# Phase 5.3 — Stable Identity, Duplicate Detection and Explicit Lineage

## Scope
This phase adds technical identities for incoming legal documents and their constituent records. It does not rewrite active bank JSON, merge records, decide legal equivalence, or infer amendment/repeal effects.

## Identity model
- `document_family_id`: deterministic key from jurisdiction, authority ID, document kind and normalized title. It groups candidate versions under a technical family; it is not proof they are the same legal instrument.
- `document_version_id`: deterministic key from family ID and original PDF SHA-256. A changed source PDF digest creates a distinct version.
- `logical_record_id`: deterministic key from family ID, record kind and normalized locator. It allows comparison of the same apparent article/section across versions.
- `version_record_id`: deterministic key from document version, record kind, locator and normalized text digest.
- `input_record_id` remains preserved; generated IDs do not overwrite user/source IDs.

Persian identity normalization applies Unicode NFKC, common Arabic/Persian character harmonization, digit normalization, diacritic/tatweel removal and whitespace folding. Original text and original record SHA-256 remain untouched.

## Duplicate scan
New package creation scans existing staging and quarantine packages. It reports same source version, exact normalized content at a logical locator, or same logical locator with different content. These are review signals only. No automatic deduplication, record deletion, package replacement, or merge occurs. A matching record at a locator with changed text may reflect amendment, extraction variance, or unrelated content; the system does not decide which.

## Lineage
Optional `lineage_relations` must be explicitly supplied and include source document ID, target document ID, allowed relation type, and reviewer ID. Supported relation types: `amends`, `repeals`, `replaces`, `interprets`, `implements`, `related_to`, `same_document_version`. Invalid supplied lineage routes the package to quarantine. Even a valid human-entered relation is marked `legal_effect_confirmed=false`; legal effect/currentness requires separate review.

## Package additions
- `identity_manifest.json`
- `duplicate_report.json`
- `lineage_report.json`

## Safety
- Active bank files are not read for writing or changed.
- Staging/quarantine are the only scanned package locations.
- No network access is used.
- Technical identity is not legal authenticity, authority, currentness, or equivalence.
- No automatic merge or import is performed.
