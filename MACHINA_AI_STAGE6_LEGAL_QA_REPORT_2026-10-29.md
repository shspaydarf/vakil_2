# MACHINA AI Stage 6 — General Legal Q&A Quality

Date: 2026-10-29

## Scope

This stage improves the system instruction used by `ask_ai_question` for general legal Q&A. It does not alter database schemas, legal JSON datasets, API contracts, or the Telegram routing flow.

## Changes

- Clarifies that jurisdiction must not be assumed when the question does not establish it and the answer depends on it.
- Encourages one or a small number of decisive follow-up questions when essential facts are missing, instead of asserting a definitive conclusion or overwhelming the user.
- Strengthens the distinction between user-provided facts, allegations, assumptions, and model analysis.
- Clarifies that a source's presence/title match does not prove that it supports a claim; precise legal citations require reliable source text in the input.
- Adds caution for current-law / amendment claims and date-sensitive legal deadlines.
- Recommends a concise, proportional response structure rather than forcing long templates on simple questions.
- Preserves existing privacy behavior: general Q&A sends only the question unless case context and/or a standard prompt were explicitly selected by the caller.

## Tests

- Added `tests/test_ai_stage6_legal_qa.py` with four tests for jurisdiction ambiguity, citation caution, and explicit case-context handling.
- Focused tests: 13 passed.
- Full test suite: 119 passed.
- `python -m compileall -q legal_bot`: PASS.
- `python preflight.py`: PASS (syntax, JSON parse, core files/data, callback fallback).

## Limitations

- These are prompt-level and integration-contract tests using a mocked `_call`; no live external-model or Telegram test was run.
- This change cannot guarantee factual/legal correctness and does not implement live legal-source retrieval or verification. Those remain separate work items.
