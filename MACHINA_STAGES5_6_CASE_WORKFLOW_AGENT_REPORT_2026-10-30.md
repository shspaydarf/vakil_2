# MACHINA — Stages 5 & 6: Supervised Case Workflow Agent

## Scope
Implemented a deterministic orchestration module over existing local document search and multi-document fact comparison. No database schema, law data, Gramophone, Telegram menu, external model call, or document upload behavior was changed.

## Stage 5 — workflow design
The workflow is explicitly staged: `search` → `extract_compare` → `lawyer_review` → `complete`. Each stage requires an explicit approval recorded against the current step. Declining pauses the workflow. State is JSON-serializable so a caller can persist it using an approved persistence layer later.

## Stage 6 — implementation
Added `legal_bot/case_workflow_agent.py` with:
- `create_case_workflow`: creates a versioned checkpoint.
- `approve_step`: records explicit approval or pauses on decline.
- `run_approved_step`: executes one approved local step only.
- `workflow_summary`: produces a compact UI-safe status summary.

The agent reuses `search_case_documents` and `analyze_case_documents`. The caller must pass documents already authorized and scoped to one case. The module does not independently fetch documents, so it cannot broaden access. It does not autonomously draft, send, file, or make legal conclusions. Results remain review candidates and a lawyer review step is explicit.

## Tests
Added five tests covering approval gating, staged progression, source provenance, pause-on-decline, and lawyer-review flag. Full suite: **160 passed, 0 failed** (`pytest -q`, 13.85s).

## Not yet completed
- Telegram/Mini App UI callbacks and user-facing controls are not connected.
- Durable checkpoint persistence is not wired into the UI; the returned state is JSON-serializable for that future integration.
- Live Telegram and external service tests were not performed.
- The agent does not autonomously call external AI or perform consequential actions.
