# MACHINA Growth Batch 21 — Stage 1: Case Dashboard Data Contract & Existing Infrastructure Audit

**Date:** 2026-10-31  
**Base:** MACHINA Growth Batch 20 — Stage 4 Search QA  
**Scope:** Read-only architecture/data audit and dashboard contract design. No application logic, database schema, API behavior, or Mini App UI was changed in this stage.

## Executive decision

Build the Smart Case Dashboard as an aggregation/presentation layer over the existing case services, repositories, database tables, and deterministic analysis engines. Do **not** create duplicate tables or replacement timeline/evidence/issue engines.

The existing `ProductCaseService.workspace()` is the natural orchestration boundary. Stage 2 should extend this service (or a small dashboard composer called by it) and preserve its user-scoped access checks. The Mini App should continue to use the existing case workspace route and receive a versioned dashboard payload.

## 1. Existing infrastructure inventory

### 1.1 Case identity and metadata

| Data | Existing source | Current fields / notes | Dashboard use | Status |
|---|---|---|---|---|
| Case identity | `cases` via `CaseRepository.get()` / `CaseService.get()` | `id`, `user_id`, `file_name`, `status`, `created_at`, `updated_at` plus migrated workspace fields | Header, lifecycle, update time | Exists |
| Workflow stage | `cases.stage` | Values validated by `CaseService`: `new`, `intake`, `research`, `review`, `drafting`, `closed` | Stage badge | Exists |
| Priority | `cases.priority` | `low`, `normal`, `high`, `urgent` | Priority badge / sorting | Exists |
| Lawyer's next action | `cases.next_action` | Free text, max 1,000 chars in service | Explicit lawyer-entered next step | Exists |
| Archive state | `cases.status`, `archived_at`, `archived_from_status` | Archived case is separately handled | Archived/read-only state | Exists |
| Case pin | `case_pins` | User/case scoped | Optional quick marker | Exists |

### 1.2 Documents and source material

| Data | Existing source | Current fields / notes | Dashboard use | Status |
|---|---|---|---|---|
| Current documents | `case_documents`, `get_case_documents()` and `DocumentService.public_list()` | `id`, `case_id`, `file_name`, `page_count`, `extracted_text`, `created_at`, storage metadata | Document count, extraction availability, open source | Exists |
| Historical versions | `case_versions`, `get_case_versions()` | `version_no`, file name, page count, extracted text, timestamps, storage metadata | Version count and historical comparison entry point | Exists |
| Additions | `case_additions` | Addition number, file count, created time | Optional document intake context | Exists |
| Extracted text | `get_case_text()` | Combined current-document text | Analysis input and text coverage | Exists |
| Source locations | Existing engine provenance | Document IDs/names, page labels, character spans where produced | Source-linked alerts and timeline | Partial; depends on engine output |

**Known limitation:** `build_case_chronology()` explicitly analyzes current case documents and reports whether historical versions exist, but excludes historical versions from its chronology. Do not imply the dashboard timeline covers every historical version.

### 1.3 Lawyer notes, tasks, events, and dates

| Data | Existing source | Current fields / notes | Dashboard use | Status |
|---|---|---|---|---|
| Private lawyer note | `case_lawyer_notes` via `get_case_lawyer_note()` / repository note functions | `case_id`, `user_id`, `note_text`, `updated_at` | Note-exists indicator / recent update only; do not expose full note in dashboard by default | Exists |
| Case tasks | `case_tasks` via `list_case_tasks(uid,cid,include_done,limit)` | `id`, `user_id`, `case_id`, `title`, `due_at`, `done`, `created_at`, reminder fields | Open/overdue/upcoming task counts and short list | Exists |
| Case events | `case_events` via `list_case_events(uid,cid,limit)` | `event_type`, `title`, `details`, `created_at` | Recent activity / case actions | Exists |
| Extracted important dates | `case_important_dates` via `list_case_important_dates(uid,limit)` | Jalali/Gregorian date, description, source page/text | Date panel, source-linked extracted dates | Exists |
| Date reminders | `case_date_reminders` | Explicit opt-in, one-day-before policy | Reminder status | Exists |
| User-wide tasks | `user_tasks` / calendar functions | Tasks not necessarily linked to a case | Exclude from a single-case dashboard unless explicitly labeled as global | Exists elsewhere |

### 1.4 Client relationship

`clients` and `client_case_links` already link a user's clients to their cases. `db.case_workspace(uid,cid)` returns client names, but the current `ProductCaseService.workspace()` response does not include the client relationship. Stage 2 can safely add a small, user-scoped client summary; it must not include phone numbers, national IDs, or private client notes in the dashboard summary payload.

### 1.5 Existing deterministic intelligence engines

| Existing engine | Entry point | Outputs relevant to dashboard | Important caveat |
|---|---|---|---|
| Chronology | `timeline_engine.build_case_chronology(uid,cid,include_undated=True)` | `events`, `critical_events`, `conflicts`, `gaps`, date range and counts; event sources include document/page/location data | Current documents only; event status distinguishes verified text, party assertion, uncertain, conflict, inferred, undated |
| Issue extraction | `issue_engine.build_case_issues(uid,cid)` | Issue list, labels, signals, source references, counts | Issues are machine-extracted review candidates, not judicial findings |
| Evidence matrix | `evidence_engine.build_evidence_matrix(uid,cid)` | Claims, matrix, linked source spans, support/contradiction indicators, evidence gaps | Engine deliberately avoids treating the originating sentence as independent proof; statuses are review signals |
| Legal authorities | `authority_engine.build_case_authorities(uid,cid)` | Candidate legal references, verification statuses, authority gaps and counts | Corpus presence does not establish current validity/applicability |
| Strategy | `strategy_engine.build_case_strategies(uid,cid)` | Candidate strategy directions and counts | Suggestions, not instructions or legal conclusions |
| Case guidance | `case_guidance.build_case_guidance(text)` | Overview, facts, claims, issues, missing items, evidence, references, risks, contradictions, questions, actions, future dates | Local rule-based output; text sufficiency is not legal correctness |
| Existing summary composer | `ProductCaseService._build_intelligence_summary(...)` | Risk label, findings, recommended actions, open questions, evidence gaps, confidence metadata | Explicitly labels confidence low and rule-based / not semantically validated |

**No replacement engines are required for the dashboard.** Stage 2 should normalize and summarize their existing outputs while preserving source metadata and caveats.

### 1.6 AI, drafts, and workflow capabilities

| Data | Existing source | Dashboard use | Status |
|---|---|---|---|
| AI history | `case_ai_history` via `get_case_ai_history()` / `ProductCaseService.ai_history()` | Count and most recent user-triggered interaction only | Exists |
| Draft artifacts | `drafting_artifacts` via `latest_draft_artifact()` / `list_draft_artifacts()` | Latest draft status/version and shortcut | Exists |
| Draft review events | `drafting_review_events` and drafting API | Human review state / pending review marker | Exists; confirm exact aggregation in Stage 2 |
| Workflow agent | Existing case workflow agent service/API | Current workflow state and shortcut | Exists separately; not included in current workspace contract |
| Multi-document analysis | Existing cross-document API/engine | Shortcut and last-run output only if a durable record exists | Exists as a feature; durable last-run summary needs verification |

AI must remain user-triggered. Opening or refreshing the dashboard must not call an AI provider, consume credits, or silently send case content externally.

### 1.7 Existing orchestration/API/UI

- `legal_bot/core/product.py` — `ProductCaseService.workspace()` is the canonical product-level aggregator.
- `legal_bot/api.py` — existing authenticated `GET /api/v1/cases/{id}/workspace?deep=...` route calls that service.
- `miniapp/app.js` — `openCase()` fetches the workspace; `renderWorkspace()` renders the existing case landing page.
- Dedicated routes already exist for case tasks, timeline, evidence, document search, multi-document analysis, AI history, drafting, and notes.
- The Mini App currently uses the workspace as a tool-launcher/overview, with deeper content in separate views.

## 2. Current contract gap analysis

The existing workspace response currently includes:

- `case`
- `documents`, `document_count`, `text_chars`
- `intelligence` (`chronology`, `issues`, `evidence`, `authorities`, `strategies`, `guidance`, `summary`)
- `ai.history` and history count
- `drafting.latest`, draft versions and count
- capability flags

The following useful data is **not currently composed into the ProductCaseService workspace response**, even though it exists in DB or dedicated APIs:

1. Open case tasks, completed-task count, overdue/upcoming task summaries.
2. Important dates and their reminder status.
3. Recent case events/activity.
4. Client names/relationship summary.
5. Lawyer note existence/updated timestamp (not its full text).
6. Document extraction/quality counts (text available, text missing, pages if available).
7. A normalized dashboard alert list with a source pointer and severity basis.
8. Data coverage/limitations for the dashboard snapshot.

The current `workspace(include_deep_intelligence=False)` implementation still builds chronology, issues, evidence, authorities, strategies, and guidance before trimming the response. The flag currently reduces payload detail but does not avoid the expensive engine calls. Stage 2 should address this deliberately, with tests, rather than assuming `deep=0` is a cheap dashboard preview.

## 3. Proposed versioned dashboard data contract

This is a **design contract only**. It is not implemented in Stage 1 and must be reviewed against existing naming conventions during Stage 2.

```json
{
  "dashboard_contract_version": 1,
  "case": {
    "id": 0,
    "name": "",
    "status": "",
    "stage": "",
    "priority": "",
    "next_action": "",
    "created_at": "",
    "updated_at": "",
    "archived": false
  },
  "people": {
    "client_names": [],
    "count": 0
  },
  "overview": {
    "document_count": 0,
    "documents_with_text": 0,
    "documents_without_text": 0,
    "version_count": 0,
    "open_task_count": 0,
    "overdue_task_count": 0,
    "upcoming_task_count": 0,
    "important_date_count": 0,
    "recent_event_count": 0,
    "issue_count": 0,
    "claim_count": 0,
    "evidence_gap_count": 0,
    "timeline_event_count": 0,
    "timeline_conflict_count": 0
  },
  "intelligence": {
    "summary": {},
    "issues_preview": [],
    "evidence_preview": [],
    "timeline_preview": [],
    "authorities_summary": {},
    "guidance_summary": {}
  },
  "attention": {
    "alerts": [],
    "basis": "deterministic_local_rules",
    "confidence": "low"
  },
  "tasks": {
    "next": [],
    "overdue": [],
    "open_count": 0
  },
  "dates": {
    "upcoming": [],
    "reminder_policy_note": ""
  },
  "recent_activity": [],
  "documents": {
    "latest": [],
    "quality": {}
  },
  "drafting": {
    "latest": null,
    "version_count": 0,
    "human_review_required": true
  },
  "ai": {
    "history_count": 0,
    "latest_activity_at": null,
    "user_triggered": true,
    "auto_invoked": false
  },
  "data_quality": {
    "coverage": {},
    "limitations": [],
    "generated_at": ""
  },
  "navigation": {
    "documents": "",
    "timeline": "",
    "evidence": "",
    "tasks": "",
    "ai": "",
    "drafts": ""
  }
}
```

### Alert record shape

Each alert should be a review lead with explicit provenance, not a free-floating AI statement:

```json
{
  "id": "",
  "type": "deadline|timeline_conflict|evidence_gap|missing_text|overdue_task|unverified_authority",
  "severity": "info|warning|high",
  "title": "",
  "message": "",
  "source": {
    "kind": "document|task|important_date|timeline_event|evidence_claim|authority",
    "id": null,
    "document_id": null,
    "page": null
  },
  "created_at": null,
  "action_label": "بررسی منبع",
  "action_target": ""
}
```

Severity must be rule-derived and conservative. A missing evidence link is not proof that evidence does not exist. An extracted date is not automatically a statutory deadline. A legal authority candidate is not automatically current or applicable.

## 4. Data ownership and privacy rules

1. Every repository read must use the authenticated `uid` and requested `case_id`; never trust a user ID from the browser payload.
2. Verify case ownership before loading child resources. Prefer joins that enforce both `case_id` and `user_id` where the table has both.
3. Never expose `clients.phone`, `clients.national_id`, or private client notes in the dashboard overview.
4. Do not return full lawyer-note text in the dashboard summary; at most return `has_note` and `updated_at`.
5. Do not put full extracted document text, full AI prompts/answers, or full draft bodies in the dashboard overview. Use counts, bounded previews, and existing dedicated detail routes.
6. Archived case access must follow the existing authenticated case route policy; do not silently include archived child records in active dashboards.
7. No AI/provider invocation on dashboard open or refresh.
8. Every alert and extracted insight must retain its source kind and, where available, document ID/page/character range.

## 5. Stage 2 implementation plan (no coding in Stage 1)

1. Add a small `CaseDashboardService` or a focused composer within `ProductCaseService`; reuse current repositories and engines.
2. Load tasks, dates, events, clients, note metadata, document metadata, drafts, and AI-history metadata with strict user/case scope.
3. Reuse existing intelligence engines once per snapshot; avoid recomputing timeline through issue/evidence builders if a safe shared snapshot/refactor is possible.
4. Normalize compact previews and counts into the versioned contract above.
5. Keep the current workspace response backward compatible; add a `dashboard` object or versioned route only after checking existing frontend consumers.
6. Make `deep=0` genuinely avoid deep engine calls or rename/document its semantics; do not return a misleading lightweight contract.
7. Add tests for ownership isolation, archived cases, no AI invocation, provenance, empty cases, missing OCR text, and stable response shape.

## 6. Stage 3–5 dependencies

- Stage 3 alerts/actions must consume only the normalized data contract and must not write to the case or mark an item complete automatically.
- Stage 4 UI should replace/reorganize the existing `renderWorkspace()` rather than create a second case dashboard.
- Stage 5 should test realistic case fixtures: empty, multi-document, missing extracted text, conflicting dates, evidence gaps, overdue tasks, upcoming dates, historical versions, and two separate user accounts.

## 7. Validation of this audit package

- `pytest -q`: **316 passed** on the unmodified Batch 20 Stage 4 codebase.
- No source code or database schema changed in this stage.
- This is a source-code audit and contract proposal, not a live Telegram/WebView test or production database inspection.

## Explicit out-of-scope items

- No new tables or migrations.
- No AI prompts, model calls, embeddings, or automatic legal conclusions.
- No redesign of the Mini App in Stage 1.
- No claim that existing extraction/analysis is complete or legally verified.
