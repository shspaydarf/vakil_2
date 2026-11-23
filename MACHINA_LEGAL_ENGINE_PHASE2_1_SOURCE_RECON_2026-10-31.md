# MACHINA — Legal Engine Phase 2.1: Source Reconnaissance
Date: 2026-10-31

## Scope and safety boundary
This is a read-only reconnaissance pass. No production Python code, active legal JSON, search indexes, Mini App files, or quarantine records were changed. No documents were imported into the active corpus. The goal is to map source categories, page patterns, downloadable assets, and access risks before implementing connectors.

## Executive result
- **Ekhtbar:** publicly indexed category pages expose useful, separable legal-document categories and some direct PDF/ZIP downloads. It is a useful discovery/indexing source, not proof of authenticity or current legal force.
- **Majles Research Center legacy law portal (`rc.majlis.ir/fa/law`):** search indexing confirms the historical law portal and a stable-looking `print_version/<numeric-id>` page pattern. Direct browser retrieval of the portal returned HTTP 502 in this inspection, so live pagination, search form parameters, and current PDF/download behavior remain unverified. This is an access observation, not proof that the site is offline for all clients.
- **Pilot recommendation:** begin with a small Ekhtbar Supreme Court unity-of-precedent PDF sample because the category has a clear archive page and explicit year-separated PDF links. In parallel, continue a separate Majles connectivity probe. Do not use Ekhtbar to certify a law's status or replace issuing-authority confirmation.

## A. Ekhtbar reconnaissance
Base domain: https://www.ekhtebar.ir/

### Observed navigation categories
The inspected archive page exposes these distinct categories in the site's navigation:
- مجموعه قوانین
- آرا وحدت رویه
- نظریه‌های مشورتی
- مصوبات
- طرح و لایحه
- نظریه‌های رییس مجلس شورای اسلامی
- نشست‌های قضایی
- آیین‌نامه‌ها
- بخشنامه‌ها
- آرای دیوان عدالت اداری
- رویه قضایی
- سیاست‌های کلی

### Confirmed archive pattern: Supreme Court unity-of-precedent rulings
Archive page:
https://www.ekhtebar.ir/بانک-آراء-وحدت-رویه-دیوان‌عالی-کشور/

The page lists a bulk ZIP for rulings from 1323–1396 and year/range-separated PDF links, including 1404 (through Mehr), 1403, 1402, 1401, and older periods. The page identifies the collection as prepared by the General Directorate for Unification of Procedure and Publication of General Board Proceedings and Rulings. This is useful provenance metadata, but the underlying issuer source should still be checked before treating the copy as authoritative.

A 1404 PDF link was followed successfully. It resolved to a direct PDF under `/wp-content/uploads/2023/01/` and the browser's text extraction returned severely garbled/near-empty Persian text. This suggests that extraction quality must be assessed from the actual PDF (font mapping, scan/image content, or encoding), not inferred from the fact that it is a PDF. Phase 3 should inspect page images and run the existing PDF/OCR pipeline.

### Confirmed archive pattern: advisory opinions
Category page:
https://www.ekhtebar.ir/category/قوانین-و-مصوبات/نظریه-های-مشورتی/

Search indexing showed dated individual posts with structured metadata such as opinion number, case/file number, and opinion date, plus the question and answer text. Monthly compilation posts also exist; a 1405 monthly archive post says the General Directorate of Legal Affairs has published monthly compilations since Shahrivar 1398. A separate archive page lists monthly PDFs across multiple years.

The category page was indexed and searchable, but direct opening during this pass redirected to a JavaScript/browser challenge. Therefore, do not assume that a simple HTTP client can fetch every page. Connector implementation must detect challenge/403/429 responses, back off, and stop rather than bypass access controls.

### Ekhtbar constraints and design implications
1. WordPress-style category/archive structure appears usable for discovery, but pages may be protected by a browser challenge.
2. Direct media links can exist beneath `/wp-content/uploads/...`; filenames and folder dates are not reliable document dates.
3. A post may contain HTML text, a monthly PDF, a ZIP, or several links; the connector must collect all candidate assets and preserve the referring page URL.
4. Archive labels may be stale or have a date range that differs from the actual latest document. Extract metadata from each asset and compare it with the page.
5. PDF text extraction may fail despite a successful download. Phase 3 must classify text-native, image-only, and malformed/font-mapped PDFs.
6. No automated active-corpus import based solely on Ekhtbar content.

## B. Majles Research Center portal reconnaissance
Historical portal: https://rc.majlis.ir/fa/law

Search-index evidence confirms a law portal with paths including:
- `/fa/law/`
- `/fa/law/search/`
- `/fa/law/print_version/<numeric-id>`

An indexed example points to:
https://rc.majlis.ir/fa/law/print_version/929088

The indexed page describes a law record with a title, navigation breadcrumb, and a printable version. However, direct retrieval of `https://rc.majlis.ir/fa/law` returned HTTP 502 in the current browser inspection. Consequently, the following remain **unverified** and must be probed from the eventual deployment environment before coding a production connector:
- whether the legacy portal is consistently reachable;
- search query parameter names and pagination;
- whether record IDs are stable and sequential;
- whether records expose HTML, PDF, or both;
- whether downloadable files are linked directly or generated dynamically;
- robots/terms/rate-limit requirements.

Do not replace this source with an unofficial mirror just because the legacy portal is temporarily inaccessible. The source connector should report `source_unavailable` or `retry_later` and retain the failed probe details.

## C. Source role and trust policy
| Source | Intended role | What it can establish | What it cannot establish by itself |
|---|---|---|---|
| Majles / Parliament sources | Preferred discovery and checking route for parliamentary legislation | A parliamentary record and its published text, subject to source verification | Current force after later amendments/repeal unless checked against authoritative status/version sources |
| Ekhtbar | Discovery, indexing, convenient archives and candidate copies | Existence of a published candidate document and useful metadata | Authenticity, completeness, official publication status, or current legal force |
| Issuing court / official legal department | Final verification for rulings/opinions | Issuer-published record and source-of-origin confirmation | Subsequent legal effect unless the relevant status/history is checked |

## D. Proposed connector behavior (design only; not implemented yet)
Each source connector should emit a normalized *candidate document* record and must not write to `laws.json`, `rulings.json`, `consultations.json`, or any active JSON bank.

Minimum fields:
- `source_id`
- `source_name`
- `source_role` (`primary_discovery`, `secondary_discovery`, `issuing_authority`)
- `document_type`
- `title`
- `page_url`
- `asset_url` (nullable; one candidate per asset)
- `source_record_id` (nullable)
- `issuer` (nullable)
- `document_number` (nullable)
- `document_date` (nullable)
- `page_date` (nullable)
- `discovered_at`
- `http_status`
- `content_type`
- `content_length` (nullable)
- `discovery_status`
- `notes`

Connector safety:
- Use conservative request rates and bounded pagination.
- Identify the client honestly; use a clear user agent/contact where appropriate.
- Respect robots directives, published terms, access controls, and server errors.
- Do not solve, evade, or automate browser challenges/CAPTCHAs.
- Retry transient errors with backoff; stop on persistent 403/429/challenge responses.
- Preserve original URLs and referring page; never infer an official source from a mirrored file path.
- Store candidates in the ingestion registry/staging area only.

## E. Recommended implementation order
1. Build a small generic connector interface and a local fixture-based test harness.
2. Implement Ekhtbar archive discovery for one bounded category: Supreme Court unity-of-precedent rulings.
3. Extract candidate links and metadata only; no downloads in this first connector test.
4. Add an optional, low-volume asset download probe after link discovery passes QA.
5. Separately probe Majles reachability and legacy route behavior from the actual deployment environment.
6. Only after both connectors pass access and stability checks, expand to advisory opinions and parliamentary laws.

## F. Acceptance criteria for Phase 2
- A connector can enumerate candidates without modifying active JSON.
- Every candidate retains a source page URL and, where present, a direct asset URL.
- Category/document type is explicit; laws, rulings, opinions, circulars and court-session reports are not mixed.
- Pagination is bounded and repeatable.
- HTTP errors/challenges are reported, not bypassed.
- Duplicate discovery of the same candidate is idempotent.
- Unit tests use saved HTML fixtures and do not depend on live websites.
- Live tests are low-volume and opt-in.

## Sources inspected
- Ekhtbar Supreme Court unity-of-precedent archive: https://www.ekhtebar.ir/بانک-آراء-وحدت-رویه-دیوان‌عالی-کشور/
- Ekhtbar advisory-opinion category: https://www.ekhtebar.ir/category/قوانین-و-مصوبات/نظریه-های-مشورتی/
- Ekhtbar monthly advisory-opinion archive: https://www.ekhtebar.ir/بانک-نظریههای-مشورتی-اداره-کل-حقوقی/
- Majles legacy law portal: https://rc.majlis.ir/fa/law
- Indexed Majles print-version example: https://rc.majlis.ir/fa/law/print_version/929088
