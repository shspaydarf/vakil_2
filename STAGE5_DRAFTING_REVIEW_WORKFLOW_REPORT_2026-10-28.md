# LegalBot — Stage 5: Draft Review Workflow

Date: 2026-10-28

## Objective
Complete the drafting workflow with explicit, case-scoped review events while preserving generated draft artifacts as immutable versions.

## Changes

- Added `drafting_review_events`, an append-only event table associated with a specific user, case, and immutable draft artifact.
- Added `record_draft_review`, `list_draft_reviews`, and `get_draft_review` service functions.
- Added API routes:
  - `GET /api/v1/cases/{case_id}/drafts/{artifact_id}/reviews`
  - `POST /api/v1/cases/{case_id}/drafts/{artifact_id}/review`
- Review decisions are constrained to `reviewed_ok` and `changes_requested`.
- A review event requires explicit confirmation; notes are capped at 8,000 characters.
- Review writes are rejected for archived cases and for drafts not owned by the authenticated user/case pair.
- The Mini App can open prior draft versions, view review history, and record a review decision with a note.
- The original draft text is not modified by review actions; each action creates a separate history event.
- UI/API language explicitly avoids claiming that an account's review action proves professional identity, legal correctness, or formal legal approval.

## Validation

- Pytest: **69 passed**
- Preflight: **PASS**
- Python compile: **PASS**
- Mini App JavaScript syntax: **PASS**
- ZIP integrity: checked after packaging

## Limitations / follow-up

- The current account model does not establish a separate lawyer role or professional identity. Review events record the authenticated account's explicit action only.
- This stage does not provide collaborative editing, redlining/diff between draft versions, digital signatures, PDF/DOCX export, or a legally qualified approval workflow.
- Review events are append-only at the application level, not cryptographically tamper-evident. Database administrators can still alter database contents.
- No live Telegram deployment or production-host end-to-end test was performed in this environment.
