# MACHINA — Supervised Workflow Agent Integration Report

Date: 2026-10-30

## Delivered

- Added a dedicated durable store `case_workflow_agent_sessions`, scoped by `(user_id, case_id)` and linked to the existing user/case tables.
- Added authenticated Mini App API routes:
  - `GET /api/v1/cases/{case_id}/workflow-agent`
  - `POST /api/v1/cases/{case_id}/workflow-agent/start`
  - `POST /api/v1/cases/{case_id}/workflow-agent/approve`
  - `POST /api/v1/cases/{case_id}/workflow-agent/run`
- Added the `عامل گردش کار` card to the case workspace and a Persian UI for status, step approvals, execution, results, and action history.
- Persisted the workflow checkpoint and bounded action history after each state transition.
- The workflow uses the existing local document search and multi-document extraction/comparison modules. Documents are loaded server-side only after verifying ownership of the requested case.
- Archived cases cannot start or execute this workflow.

## Supervision and safety boundaries

- Steps remain `search` → `extract_compare` → `lawyer_review` → `complete`.
- Every step requires explicit lawyer approval before execution.
- Declining pauses the workflow; resuming requires another explicit approval.
- The agent does not invoke external AI, draft legal documents, send/file anything, or make legal conclusions.
- Search and analysis findings are candidates only; source documents remain authoritative and lawyer review is required.

## Validation

- `python -m compileall -q legal_bot`: passed.
- `node --check miniapp/app.js`: passed.
- Full automated suite: **172 passed, 0 failed**.
- Local HTTP API lifecycle smoke test: passed through start, approval and execution of all four steps, persistence reload, and `COMPLETED` status.

## Not yet validated

- Live deployment against the production database/server.
- Telegram WebApp authentication in the live Telegram client.
- Real-world case documents and user acceptance testing.
- Background execution: deliberately not added; each step is user-triggered and runs synchronously in the API request.

## Release note

This is a supervised, deterministic workflow integration, not an autonomous legal agent. No existing classic Telegram menu, legal dataset, or document-ingestion behavior was intentionally changed.
