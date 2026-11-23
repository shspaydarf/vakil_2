# MACHINA Growth Batch 21 — Stage 2: Case Dashboard Aggregator

Date: 2026-10-31
Base: Batch 21 Stage 1 (case dashboard audit + versioned data contract)

## Delivered

- Added a centralized, UI-agnostic `dashboard` object to `ProductCaseService.workspace()` while preserving the existing workspace fields and contract version.
- Aggregates case metadata, client names only, operational tasks, extracted important dates, recent case events, document text-extraction quality, lawyer-note existence/update time, drafting metadata, and AI-history metadata.
- Adds bounded deterministic attention items for overdue tasks, near extracted dates, timeline conflicts, evidence gaps, missing extracted text, and unverified legal-authority candidates.
- Adds source-kind/source-ID and available document/page provenance to attention items, plus navigation targets.
- Explicitly labels the attention layer as deterministic and low-confidence; includes limitations clarifying that extracted dates are not automatically statutory deadlines, evidence gaps do not prove evidence is absent, and candidate legal sources are not automatically valid/applicable.
- Dashboard avoids client phone/national-ID data, lawyer-note bodies, extracted source text, AI prompts/answers, and draft body content in its dedicated summary fields.
- Uses authenticated owner ID and case ID in all new database reads.
- Uses Tehran-local date for overdue/upcoming calculations.
- Fixed `include_deep_intelligence=False` so it truly skips chronology, issue, evidence, authority, strategy, and guidance engines. Existing workspace keys remain available with safe empty/uncalculated placeholders in lightweight mode.

## Compatibility and scope

- No database migration or schema change.
- No new AI/provider call; opening the dashboard remains AI-free.
- No Mini App visual rewrite in this stage. Existing API workspace route automatically carries the additive `dashboard` field; the frontend consumption/presentation is reserved for Stage 4.
- Existing workspace keys (`case`, `documents`, `intelligence`, `ai`, `drafting`, `capabilities`) remain present.

## Validation

- `pytest -q`: 318 passed.
- `node --check miniapp/app.js`: passed.
- `python -m compileall -q legal_bot tests`: passed.
- `python preflight.py`: passed.
- ZIP integrity (`ZipFile.testzip()`): passed.
- Added tests for operational aggregation/privacy boundaries and proof that lightweight mode does not invoke deep engines.

## Known limitations / next stage

- The dashboard aggregator is now available in the API response, but the Mini App does not yet render the new dashboard cards; that belongs to Stage 4 after Stage 3 alert/action prioritization is finalized.
- Extracted legal dates remain candidate dates and require human verification against source documents.
- Timeline/evidence/authority items inherit the source and confidence limitations of their existing deterministic engines.
- No real Telegram WebView/device or production deployment test was performed.
