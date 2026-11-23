# MACHINA Growth Batch 8 — Persistent Workflow Builder

Date: 2026-10-31
Base: Growth Batch 7 — Workflow Templates

## Scope delivered

- Added private, per-lawyer workflow definitions with create, edit, delete, and list operations.
- Added a workflow designer with 2–12 steps, five supported existing tool actions, per-step instructions, and a required reviewable prompt for AI steps.
- Added persistent workflow runs tied to a lawyer-owned, active case. The run stores a snapshot of the selected workflow and completion state; resuming after closing/reopening the Mini App is supported.
- Added server-side ownership checks for workflow definitions, runs, and case association. User identity comes only from authenticated Telegram Mini App context.
- Added limits: up to 50 custom workflows per lawyer, 12 steps per workflow, bounded title/description/instruction/prompt lengths.
- Workflow steps remain human-supervised. AI prompts are placed into the existing case AI question field for review; they are not auto-submitted and do not spend AI quota merely by opening a workflow step.

## AI submenu organization requested by user

- Added a dedicated Mini App AI submenu launcher.
- Moved AI-dependent tools (legal question, case analysis, evidence/issues review, drafting), guided workflows and the custom workflow builder into this submenu.
- Moved the AI prompt/template library and AI/drafting work-product history into the same submenu.
- Kept general case cabinet, calendar, recent activity, and saved documents outside the AI submenu.
- Removed the old workflow tab from the general work-library shelf to avoid duplicate navigation.

## Storage

- `lawyer_workflows`: private reusable workflow definitions.
- `lawyer_workflow_runs`: private run records with workflow snapshot, case reference, completed step indexes, and status.
- Foreign keys and user-scoped SQL predicates protect ownership boundaries.

## Validation

- Full test suite: 243 passed.
- JavaScript syntax check: passed.
- Python compileall: passed.
- `preflight.py`: PASS.
- ZIP integrity: checked after packaging.

## Not performed

- No live Telegram Mini App/browser session test.
- No production deployment test.
- No 200–300 concurrent-user load test.
- No automated external AI execution was added.

## Files added/updated

- Added `legal_bot/lawyer_workflows.py`.
- Updated `legal_bot/api.py` with authenticated workflow CRUD and run-state endpoints.
- Updated Mini App markup, JavaScript, and styles for AI submenu placement, workflow designer, and persisted progress.
- Added `tests/test_lawyer_workflows.py`.
