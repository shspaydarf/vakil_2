# MACHINA Growth Batch 7 — Guided Workflow Templates

Date: 2026-10-31  
Base: `LegalBot_MACHINA_Growth_Batch6_Review_Tables_2026-10-31.zip`

## Delivered
- Added authenticated read-only catalog endpoint: `GET /api/v1/workflow-templates`.
- Added three curated, multi-step workflows inside the existing Work Library (third tab; no new top-level navigation):
  1. Initial case review
  2. Contract review
  3. Legal draft preparation
- Each workflow contains ordered steps, short instructions, and links to existing MACHINA tools: case workspace, case documents, multi-document review table, case AI, and drafting.
- A lawyer selects an active case before starting. Each step can open its existing tool; AI steps prefill a reviewable prompt but do not submit it.
- The lawyer manually marks steps complete and explicitly ends the workflow. No AI action, document modification, drafting, legal filing, or quota consumption occurs merely by selecting a workflow.
- Workflow catalog is defensive-copy static data. No new personal-data table or schema migration was introduced.
- Styling follows the existing light green / steel visual language and uses lightweight CSS only.

## Guardrails and limitations
- The runner's current progress is held in Mini App memory only. It is not persisted across reloads, app restarts, or devices.
- This batch adds curated workflows, not a personal workflow builder, team sharing, conditional branching, automatic execution, or cross-case templates.
- Existing tools retain their own permissions and behavior. The workflow layer does not bypass case ownership or document access controls.
- AI prompts are prefilled only; the lawyer must inspect and submit them manually. AI answers remain subject to the existing verification warnings.

## Verification
- Full test suite: **239 passed**.
- `node --check miniapp/app.js`: PASS.
- `python -m compileall -q legal_bot`: PASS.
- `python preflight.py`: PASS.
- ZIP integrity check: PASS.

## Not performed
- No live Telegram Mini App/browser session was run.
- No 200–300 concurrent-user load test was run.
- No external Excel/LibreOffice test is relevant to this batch.
