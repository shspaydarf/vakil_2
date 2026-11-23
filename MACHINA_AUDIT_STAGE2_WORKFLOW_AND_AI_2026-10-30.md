# MACHINA — Audit Stage 2: Workflow Agent and Case Legal AI

Date: 2026-10-30

## Scope

This audit covers the supervised case workflow agent and the case legal-intelligence / case-AI paths in the current Mini App project. It does not certify the live Telegram deployment, the real external AI provider, or production load capacity.

## Workflow agent

### Verified path

- Mini App case workspace card opens the workflow page.
- The UI calls the authenticated case-scoped routes:
  - `GET /api/v1/cases/{case_id}/workflow-agent`
  - `POST /api/v1/cases/{case_id}/workflow-agent/start`
  - `POST /api/v1/cases/{case_id}/workflow-agent/approve`
  - `POST /api/v1/cases/{case_id}/workflow-agent/run`
- The API resolves the authenticated user from Telegram WebApp authentication; the body does not choose the owner ID.
- Case ownership is checked before state access or document loading.
- Session storage is keyed by `(user_id, case_id)`.
- Archived cases cannot start or execute the workflow.
- Each step requires an explicit approval; a decline pauses the flow.
- The workflow is deterministic and local: it calls document search and multi-document analysis. It does not autonomously call external AI, draft or file legal documents, send messages, or make legal conclusions.

### Defect found and fixed

The API previously used a read-then-write checkpoint sequence without concurrency protection. Two simultaneous approvals/runs could both read the same state and the later write could overwrite the earlier transition.

Added an atomic SQLite compare-and-swap save using `BEGIN IMMEDIATE` and the previously-read `updated_at` value. A stale concurrent request now receives HTTP 409 (`workflow_state_conflict`) and must refresh rather than overwrite a newer state.

### Remaining limitation

Each step still runs synchronously in the API request. No background queue or worker was added. Long-running analysis can therefore occupy a request thread; this must be included in the load test stage.

## Case legal intelligence and AI

### Separation of responsibilities

- The Mini App card `تحلیل حقوقی` displays deterministic local intelligence built from the chronology, issue, evidence, authority, strategy, and guidance engines. It is not itself a generative-AI result. Its confidence remains explicitly low and its source warnings remain visible.
- The separate `AI پرونده` card calls the authenticated, user-triggered `/api/v1/cases/{case_id}/ai` endpoint. It uses case context, metered entitlement reservation/commit/refund, and the configured external-data consent gate.
- The AI history route is case-scoped and owner-scoped.
- The external model is not called without `AI_EXTERNAL_DATA_CONSENT`; the lower-level provider call rejects missing consent.
- Iranian legal-source retrieval is only activated when the question explicitly names Iran/Iranian law or a recognized Iranian-law phrase. Retrieved local records are labelled as candidates, not automatically current or legally applicable.
- Page citation audit only checks whether page labels exist in the supplied context. It does not establish semantic support for the AI claim.

### Defects found and fixed

1. **Full-context truncation could silently remove document text.** The service assembled large intelligence sections first and then the AI helper clipped the combined context at 12,000 characters. The actual document section could be pushed out of the prompt.
   - Rebuilt context with explicit per-section budgets.
   - Full mode now reserves space for sampled document text as well as compact intelligence.
   - Documents mode sends document text without running the heavier intelligence engines.
   - Long text is sampled from beginning, middle, and end, with a clear coverage warning.
   - The Mini App now displays the returned context-coverage note with the answer.

2. **The shared beginning/middle/end sampler could cut off its ending excerpt.** It sliced the assembled string after adding labels, so the tail could be lost despite a test passing the overall length cap.
   - Reworked the sampler to reserve marker space before allocating excerpts.
   - The ending excerpt is now preserved within the configured character cap.

### Remaining limitations

- Full mode is a bounded sample, not a guarantee that every page or every document is read in full.
- Documents mode may also sample long text to fit the configured prompt budget.
- The current citation audit validates page-label existence only, not whether a page supports a statement.
- AI output still requires lawyer review; no legal conclusion or citation is certified by this feature.
- Real provider latency, availability, token cost, and response quality were not tested against a live API in this audit.

## Validation

- Full automated suite: **196 passed, 0 failed**.
- Workflow pure-state tests: passed.
- Workflow persistence and stale-write compare-and-swap tests: passed.
- Workflow API conflict handling test: passed.
- Workflow API full lifecycle test (start, approve, run each step, reload persisted `COMPLETED` state): passed with controlled test documents.
- AI context-budget tests: passed.
- Documents-mode bypass tests for intelligence engines: passed.
- External-data consent gate test: passed.
- Python compileall: passed.
- `node --check miniapp/app.js`: passed.
- `python preflight.py`: PASS.

## Not certified by this report

- Live Telegram WebApp authentication and production routing.
- Live external AI provider calls or real case data quality.
- Visual verification on actual Telegram Android/iOS WebViews.
- 200–300 concurrent users or production capacity.
- Background execution and multi-process deployment characteristics beyond the tested SQLite compare-and-swap behavior.
