# MACHINA Growth Batch 20 — Stage 1: Unified Search Source Audit

Date: 2026-10-31  
Base: Growth Batch 19 — Visual Cohesion  
Stage status: inventory and architecture audit complete; no production search behavior changed in this stage.

## Purpose

Identify every existing search surface and every useful, owner-scoped content source before building one central search experience. Preserve the existing legal-search and case-document-search flows; the unified search will orchestrate them rather than replace their source-specific behavior.

## Existing search surfaces

| Existing surface | Current implementation | Current scope / limitation |
|---|---|---|
| Case list search | `GET /api/v1/cases?q=` → `CaseService.list` → `CaseRepository.list` | Searches case name only (`cases.file_name`); does not search document text or case metadata. |
| Case document search | `GET /api/v1/cases/{id}/search?q=` | Searches extracted text of documents in one explicitly selected owned case; returns document ID, filename, page/line when extraction provides them, and snippets. |
| Telegram global search | `globalsearch_cb` → `awaiting_global_search` message handler | Currently intended to search cases but calls `search_cases(uid, value, 20)`, which is not defined in `legal_bot` or imported into `handlers.py`. This path is a latent runtime `NameError` and is not a functioning full-text global search. |
| Legal research search | `GET /api/v1/legal-search?q=` → `laws.search_legal_research` | Searches the bundled legal research corpus with Persian-aware lexical ranking, expanded terms and source metadata. It is separate from private workspace search. |
| Glossary lookup | `glossary.lookup` called with legal search | Exact/alias-oriented lookup; useful as a distinct result group, not a substitute for full-text search. |
| Work-product search | `GET /api/v1/work-products?q=` | Searches current user's persisted AI exchanges and saved drafting artifacts; returns excerpts and metadata. |
| Personal lawyer library search | `GET /api/v1/lawyer-library?q=` | Searches user's own prompts/templates plus shared starter resources. Existing results are limited to 100 personal items and starter resources. |
| Student practice | Quiz catalog/session endpoints | Educational question bank, not professional matter search; keep outside the lawyer's unified workspace search by default. |

## Searchable data inventory

### A. Private lawyer workspace — candidate sources for the unified search

1. **Cases** (`cases`): name, status, stage, priority, next action, timestamps. Search only rows belonging to the authenticated user. Archived cases should be separately filterable and excluded by default, consistent with the current case list.
2. **Current case documents** (`case_documents`): filename and extracted text. Use the existing document-level search and preserve `document_id`, filename, page/line markers, and extraction coverage warnings. Original binaries are not searchable unless text extraction succeeded.
3. **Historical case versions** (`case_versions`): filename and extracted text. Include only in an explicitly labeled “نسخه‌های قبلی” group or filter; never silently mix historical versions with current evidence.
4. **Case lawyer notes** (`case_lawyer_notes`): private note text, scoped by both `user_id` and owned case.
5. **Case events / timeline** (`case_events`): title, details, event type and date, scoped by user and case.
6. **Case tasks** (`case_tasks`) and personal tasks (`user_tasks` / legacy `tasks`): title and relevant descriptive metadata. Return case association and completion/due status; do not index reminder secrets or unrelated account data.
7. **Important dates** (`case_important_dates`): description and source text, with case/date provenance. Avoid treating extracted dates as verified facts; retain their source and review status.
8. **AI history** (`case_ai_history`): question and answer, only for the authenticated user and owned case. Search must not send the content to an external AI provider.
9. **Draft artifacts** (`drafting_artifacts`): draft title/type/text and version number, with case association. Preserve version identity and status.
10. **Personal lawyer library** (`lawyer_library_items`): title, category, description and content. Include shared starter resources as a separate source type, clearly distinguished from user-authored material.
11. **Client records** (`clients` and `client_case_links`): candidate search by client name and non-sensitive note only, if included after privacy review. Do not search or return national ID, phone number, or other direct identifiers as snippets in the first release.
12. **Saved documents / saved work products / recent activity**: these are navigation/bookmark metadata rather than independent content sources. Use them as filters/boosts or shortcut groups, not duplicate result records.

### B. Shared legal knowledge — keep as a separate source family

The legal research corpus is built from bundled JSON sources and its unified search currently includes:

- `laws.json`: 9,179 list records across 173 law/package keys (count is record entries, not necessarily 9,179 distinct enacted legal provisions).
- `rulings.json`: 286 records (159 rulings and 127 administrative court rulings).
- `consultations.json`: 179 records.
- `samples_and_circulars.json`: 98 records (78 samples and 20 circulars).
- `legal_glossary.json`: 400 glossary entries.
- `important_terms.json`: 1,478 terminology entries used in supporting legal terminology workflows.

These figures are bundled-file counts at audit time, not claims that every record is current, officially verified, or independently citable. Search ranking must remain distinct from legal validity. Existing source status, source file/page, citation envelope, verification label, and date must be preserved. Legal results must never be blended into private case-file results without a visible source-family label.

## Existing retrieval capabilities to reuse

- `legal_bot/hybrid_retrieval.py`: deterministic Persian lexical + fuzzy retrieval for normalization, morphology and limited OCR/typing variation. It is not a neural semantic model and must not be marketed as one.
- `legal_bot/analysis.py::search_case_documents`: existing per-document search with provenance.
- `legal_bot/laws.py::search_legal_research`: existing legal-corpus search and source diversity controls.
- `legal_bot/drafting_artifacts.py::list_work_products`: existing owner-scoped union of draft artifacts and AI history.
- `legal_bot/lawyer_library.py::list_lawyer_library`: existing owner-scoped personal library plus starter resources.

The next engine stage should use one normalized query pipeline and common result envelope, while delegating scoring and retrieval to the specialized existing services. Avoid one giant SQL `LIKE` query across unrelated tables.

## Gaps and defects found

1. There is no single authenticated API endpoint that searches all private workspace sources and returns grouped, provenance-rich results.
2. Case-list search only searches the case name. It does not search case notes, events, tasks, dates, versions, drafts or document contents.
3. Existing case-document search requires a case ID; it cannot search across all of the user's cases.
4. Legal research search is a separate UI and endpoint; it is not coordinated with workspace search.
5. Work products and lawyer library each have their own search field and result presentation.
6. Telegram's global search handler references an undefined `search_cases` function. It must be repaired or routed through the same safe search service during the implementation stage; it must not be treated as a working global search today.
7. There is no unified result schema for source type, case identity, source locator, matched text, score, and coverage warnings.
8. Search coverage must disclose unsearchable scans / extraction failures. A “no results” response must not imply every original file was searched.

## Privacy and security boundaries for implementation

- Derive user identity exclusively from Telegram WebApp authentication / the existing authenticated API layer; never accept `user_id` as a client-supplied search scope.
- Every private source query must include authenticated `user_id` and, where applicable, a join to `cases` verifying case ownership.
- Cross-case search must not accept arbitrary case IDs as proof of access. Case IDs returned in results must already be ownership-filtered server-side.
- Do not search payment records, subscription receipts, credentials, admin data, referral/client private contact details, or national identifiers.
- Do not transmit private workspace text to external AI. The first unified search release remains local/deterministic.
- Keep archived material out by default with an explicit include-archived filter.
- Preserve exact source identity and page/line only when the extraction layer supplies it; never invent page numbers.
- Search results are retrieval hints, not legal findings. Legal sources retain their own verification/status warnings.

## Proposed unified result groups

1. پرونده‌ها
2. اسناد پرونده‌ها (با نام سند و صفحه/سطر)
3. یادداشت‌ها و رویدادهای پرونده
4. کارها و تاریخ‌های مهم
5. پیش‌نویس‌ها و تاریخچه AI
6. کتابخانه شخصی و قالب‌ها
7. منابع حقوقی و آراء/نظریات (اختیاری و با برچسب منبع مستقل)
8. واژه‌نامه حقوقی (گروه جداگانه)

Each result should carry: `source_type`, `source_id`, `case_id` (if applicable), `case_name`, `title`, `snippet`, `matched_terms`, `retrieval_score` (only when comparable within that source family), `locator` (page/line/version/date when known), `created_at` / `updated_at`, and an explicit source/coverage note where needed.

## Four-stage execution plan

- **Stage 1 — this report:** inventory existing search surfaces, content sources, privacy boundaries and gaps. Complete.
- **Stage 2 — engine:** implement one local, user-scoped search orchestrator, common result schema, bounded per-source retrieval and tests for cross-user isolation and provenance. Repair the Telegram global-search runtime path.
- **Stage 3 — Mini App:** add one central search entry point and grouped results/filters; retain specialist search panels and legal-source detail pages, linking to them where appropriate.
- **Stage 4 — QA:** test relevance, empty results, Persian normalization, archived filtering, unsearchable OCR/scans, pagination/limits, ownership isolation, and endpoint/UI compatibility; run full suite and package.

## Baseline validation

- Full test suite on Batch 19 source: **295 passed**.
- This audit stage made no application-code changes; no endpoint, UI, schema or search ranking behavior was changed.
- No live Telegram WebView test, real multi-account isolation test against production data, or load test was run.
