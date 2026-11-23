# MACHINA Growth Batch 21 — Stage 3: Alerts & Action Prioritization

Date: 2026-10-31
Base: Batch 21 Stage 2 — Case Dashboard Aggregator

## Scope

Implemented the deterministic attention-ranking layer inside the existing case dashboard composer. Existing stores and intelligence engines remain the sources of truth; no new database tables, external AI calls, or duplicate workflow engines were introduced.

## Changes

- Added alerts for overdue case tasks and tasks with approaching due dates.
- Kept extracted case dates as review signals, with urgency based on days remaining; they are not asserted to be statutory deadlines.
- Added deterministic priority scores and three display bands: `urgent`, `soon`, and `review`.
- Ranked alerts by score, then due date, then stable alert ID to produce predictable output.
- Bounded the dashboard alert list to 20 items after ranking, so urgent actions are not crowded out by lower-priority signals.
- Added `attention.priority_summary` with counts and the top action.
- Added `attention.recommended_next_actions` as a bounded top-three list.
- Retained source references, action targets, and low-confidence/deterministic-basis labels.

## Priority policy

- Overdue task: score 100.
- Task due within 1 day: 92; within 3 days: 82; within 7 days: 70; within 14 days: 58.
- Extracted date within 1 day: 88; within 3 days: 78; within 7 days: 66; within 14 days: 54.
- Timeline conflict: 68.
- Missing document text: 56.
- Evidence review gap: 38.
- Unverified legal authority candidate: 28.

These are operational triage scores, not legal risk scores, legal advice, or a determination of limitation periods. A human must verify dates and legal sources against the original documents and official sources.

## Safety and compatibility

- Dashboard still does not invoke AI automatically.
- No new sensitive fields were added to alert payloads.
- Existing ownership-scoped reads and case workspace contract remain in place.
- No schema migration or Mini App UI change in this stage.

## QA

- `pytest -q`: 320 passed.
- `node --check miniapp/app.js`: passed.
- `python -m compileall -q legal_bot tests`: passed.
- `python preflight.py`: passed.
- ZIP integrity check: passed.

## Remaining

Stage 4 will connect the dashboard's ranked alerts and recommended actions to the Mini App case workspace UI. Stage 5 will run focused security, regression, and performance checks.
