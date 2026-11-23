# Phase 7.6 — Legal Document Structure & Relationship Graph

## Purpose
Build a review-only graph from catalog rows and the parsed structures produced by the existing ingestion pipeline. The module is deterministic apart from the informational `generated_at` timestamp and performs no network access or active-bank writes.

## Added module
`legal_bot/ingestion/document_relationships.py`

### Main API
- `RelationshipPolicy`: bounds document count, edge count, minimum title length, and whether secondary-source candidates are included.
- `build_document_graph(documents, policy=None)`: emits document/article/note/band/subitem nodes and evidence-backed candidate edges.
- `write_document_graph(graph, output_path)`: atomically writes a validated 7.6 graph artifact.

### Relationship types
- `contains_article`, `contains_note`, `contains_band`, `contains_subitem`: tentative structural hierarchy derived from the parser output.
- `mentions_document`: exact normalized title mention with page/line excerpt.
- `possible_amends`, `possible_repeals`: candidate only when an exact title mention and a recognized phrase occur together.
- `catalog_relationship_hint`: preserves catalog-supplied related IDs as unverified hints.

Every edge carries a status and evidence. Article references in the matched text are retained as evidence, not interpreted as a legal effect.

## Safety boundaries
- No assertion that a document is currently in force.
- No confirmed repeal, amendment, supersession, or legal precedence.
- No source authority inferred from document text; catalog authority labels are carried through unchanged.
- Secondary/unverified records remain visibly classified as such.
- No live crawling, download, OCR, staging promotion, or active JSON bank mutation.
- Human legal review is required before any relationship is treated as legally meaningful.

## Test coverage
Ten focused tests cover structural nodes, evidence-backed exact-title matching, amendment-candidate caution, secondary-source handling, catalog hints, invalid/duplicate IDs, policy bounds, atomic output, and stable graph hashing. A further hierarchy test covers notes, bands, and subitems.
