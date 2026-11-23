# Phase 7.2 — Source Registry

## Scope

Phase 7.2 adds a versioned, auditable registry for source authority, allowed hosts,
canonical URL roots, document classes, access policy, and human verification evidence.
It is a policy/control-plane component only: it does not perform network requests,
source discovery, downloads, PDF processing, staging, or active-bank writes.

## Trust model

- New records default to `authority_level=unverified`, `status=unverified`, and
  `access_mode=disabled`.
- `official_primary` is rejected unless the record is `verified` and contains a
  reviewer ID, review timestamp, evidence reference, and SHA-256 evidence digest.
- A domain name, HTTPS, TLS, or successful access observation does not establish
  legal authority, authenticity, promulgation, or current enforceability.
- Secondary sources remain secondary and cannot substitute for an official source.
- `polite_public_read` requires a verified record and exact host allowlisting.
- URL checks require HTTPS, an exact host, default/443 port, and a path within a
  configured canonical root. Wildcard hosts and lookalike domains are rejected.
- 403, 429, and CAPTCHA/challenge responses must stop or defer work; no bypass is
  implemented or authorized by this registry.

## Persistence and audit

`SourceRegistry` stores JSON with a schema version, monotonically increasing
registry version, source records, and an append-only audit event per upsert.
Writes use a same-directory temporary file, fsync, and atomic replace. Callers can
supply `expected_version` to reject stale concurrent updates. Every mutation requires
an actor ID and a reason.

## Usage

```python
from legal_bot.ingestion.source_registry import SourceRegistry, SourceRecord

registry = SourceRegistry("data/source_registry.json")
record = SourceRecord.from_dict({
    "source_id": "example_source",
    "display_name": "Example source",
    "publisher": "Publisher",
    "jurisdiction": "IR",
})
registry.upsert(record, actor_id="operator", reason="initial unverified registration")
```

A source remains disabled and unverified until a human supplies the required evidence
and review metadata. No production source is pre-certified by this module.

## Relationship to adjacent phases

- 7.1 produces deterministic bounded plans; 7.2 provides the source-policy records
  that later cataloguing and acquisition stages can consult.
- 7.3 may inventory documents only against eligible registry records.
- 7.4 must independently enforce network safety and stop on access challenges.
- The active legal JSON bank remains untouched.

## Limitations

This phase does not verify the current availability of Majles or Ekhtebar endpoints,
does not certify any source, and does not import live source records. Those tasks
require separate evidence-based review and safe operational probes.

## Metadata URL recognition vs. network permission

`SourceRecord.recognizes_url()` validates HTTPS, exact allowed host, and canonical root
for provenance metadata. It does **not** authorize a request. `permits_url()` adds the
verified-source and `polite_public_read` requirements and is the only method suitable
for deciding whether a public read may be attempted. This separation allows supplied
or saved HTML from an unverified source to be inventoried in quarantine without
silently granting crawler permission.
