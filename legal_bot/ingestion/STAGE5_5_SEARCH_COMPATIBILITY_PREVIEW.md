# Phase 5.5 — Isolated legal-search compatibility preview

The new `legal_search_preview.py` adapter reads only a package already placed in
`ingestion/staging/` and explicitly marked `staged_pending_human_review`.
It projects staged records into the existing legal retrieval record shape and
uses the same deterministic token expansion, corpus statistics and scoring
primitives as `legal_bot.laws.search_legal_research`.

The adapter scores a temporary in-memory corpus consisting of the current active
corpus plus the candidate records. It does **not** mutate `LEGAL_CORPUS`, search
indexes, caches, active JSON bank files, staging packages, or production search
behavior. Results are marked `staging_only_not_active` and carry candidate/record
IDs, source-page references, citation envelope, and an explicit unverified label.

Quarantine packages, malformed manifests, activation-flag violations, empty
records, and invalid queries fail closed. This is a retrieval compatibility
check only: a positive hit does not prove source authenticity, legal validity,
current force, or official-source matching. No automatic import or activation
is provided in Phase 5.5.
