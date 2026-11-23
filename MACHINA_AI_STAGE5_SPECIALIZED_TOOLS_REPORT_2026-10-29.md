# MACHINA AI Stage 5 — Specialized Legal Tools Quality Guard

Date: 2026-10-29

## Scope

This is the first low-risk implementation slice of Stage 5, focused on legal drafting output integrity. It does not claim the three specialized tools have been fully redesigned. Existing case-summary and contradiction-review prompts were inspected and left behaviorally unchanged in this slice to avoid expanding risk without dedicated evaluation cases.

## Changes

- Strengthened `draft_legal_brief` instructions to separate supplied case facts, legal sources, and tentative analysis.
- Clarified that missing evidence in the supplied text is not proof that evidence does not exist in the full case file.
- Required source markers to correspond only to source entries actually packed into the model prompt.
- Added `_guard_draft_source_markers`, which flags `[S<number>]` markers that do not correspond to supplied source entries and adds a clear review warning.
- The guard is deliberately narrow: it detects unknown source IDs, but does not prove a valid source supports the sentence where it appears.
- Added three deterministic tests for valid/invalid source markers, no-source behavior, and the drafting prompt/guard integration.

## Safety and compatibility

- No database, law JSON, API contract, case workflow, external-data consent gate, or model-call count was changed.
- No additional model/API call is made.
- The original document files are not passed by this change; the existing drafting path still receives text and supplied source records.
- A valid `[S1]` marker remains intact only if source S1 was actually included in the prompt.

## Validation

- `pytest -q`: **111 passed**.
- `python preflight.py`: **PASS** (Python syntax, JSON parsing, core files/data, callback fallback).
- The tests use mocked model output; no live external-model quality run or Telegram runtime validation was performed.

## Remaining work for Stage 5

1. Build and test a case-analysis rubric against representative anonymized cases.
2. Add structured evidence traceability checks to contradiction review (quote presence and page provenance where available).
3. Add reviewable change tracking and factual-preservation tests for rewrite/drafting outputs.
4. Evaluate the real model against the Stage 2 benchmark before claiming accuracy improvements.
