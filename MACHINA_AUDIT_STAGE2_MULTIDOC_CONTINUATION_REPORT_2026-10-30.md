# MACHINA — Audit Stage 2 (continued): Multi-document analysis

Date: 2026-10-30

## Scope
Reviewed the full path for multi-document analysis: Mini App case-workspace card, API route, case ownership check, `DocumentService.list(authenticated_user_id, case_id)`, deterministic fact extraction, cross-document comparison, and rendered results.

## Confirmed integration
- Mini App card `multiDocAnalysisCard` is present in the case workspace and its click handler calls `openMultiDocumentAnalysis()`.
- The view calls authenticated `GET /api/v1/cases/{case_id}/document-analysis`.
- The API verifies case ownership and fetches documents only through the authenticated owner + case pair. The client cannot submit arbitrary document IDs or broaden the scope.
- The analysis runs locally and deterministically; no external AI provider is called.
- The Mini App displays per-source filename, document ID, page when available, extracted value and surrounding snippet.

## Findings and fixes
1. **Unbounded aggregate text work:** the previous endpoint considered up to 50 documents, each potentially containing up to the configured 1,000,000 extracted characters. This could make one synchronous request process tens of millions of characters. Added explicit limits: 50 documents, 500,000 characters per document, and 2,000,000 characters total. Truncation and skipped documents are returned explicitly; the Mini App now warns about partial coverage and shows the affected documents.
2. **Page provenance performance:** page lookup previously rescanned all preceding text for every extracted candidate, creating avoidable repeated work on long documents. Replaced it with precomputed page-marker offsets and binary search.
3. **Missing document IDs in pure/service test inputs:** documents without IDs could be grouped as if they were one source. Added per-input fallback source identities for comparisons while keeping the public document ID unset.
4. **Ambiguous amount normalization:** stripping punctuation could make values such as `1.000` and `1000` look identical despite decimal/thousands ambiguity. Punctuated amounts remain visible as candidates but are no longer auto-normalized for cross-document matching.
5. **Source clarity in UI:** added document IDs beside source filenames, and made truncation / budget omissions visible.

## Safety and interpretation
- Extracted facts are unverified candidates, not established facts or legal conclusions.
- Different amounts/dates are comparison candidates, never automatically called contradictions.
- Ambiguous punctuated amounts are not auto-matched.
- Documents with no extracted text are reported; OCR is not silently assumed.
- Work limits may result in partial analysis. The response and UI explicitly disclose this.

## Verification
- Focused multi-document tests: 12 passed.
- Full project tests: 189 passed.
- `python -m compileall -q legal_bot`: passed.
- `node --check miniapp/app.js`: passed.
- Synthetic single-request performance check: 50 synthetic documents, each 500,000 characters; configured total budget 2,000,000 characters; 4 documents analyzed, 2,000,000 characters processed in approximately 1.425 seconds in this environment. This is a local single-request benchmark, **not** a 200–300 concurrent-user load test.
- ZIP integrity checked after packaging.
- Live Telegram WebView / production API / OCR on real user documents not tested in this environment.

## Remaining Stage 2 work
Continue with workflow-agent end-to-end behavior, then case AI/legal analysis, drafting/review, lawyer preferences and remaining auxiliary capabilities. Do not infer production readiness from the automated test suite.
