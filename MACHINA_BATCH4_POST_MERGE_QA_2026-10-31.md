# MACHINA — Post-merge QA and code line count

Date: 2026-10-31
Audited package: Batch 4 duplicate-logic merge
Comparison baseline: Batch 3 low-risk cleanup

## Scope and file-diff review

Compared the Batch 4 tree against Batch 3:
- 15 existing production Python modules changed.
- 1 shared helper module added: `legal_bot/text_utils.py`.
- 1 focused test module added: `tests/test_shared_text_utils_batch4.py`.
- 1 audit report added.
- No files removed.
- No API, database, Mini App, HTML, CSS, JavaScript, legal corpus, or legal source data files changed.

The changed production modules only redirect previously local text-cleaning, normalization, term-checking, and legal-title-hit helper logic to the shared utility module. The refactor did not alter feature routes or handlers.

## Verification

- `python -m compileall -q legal_bot tests`: passed.
- Focused Batch 4 tests: 4 passed.
- Differential checks against the pre-merge helper behavior: passed for 8 representative input cases, 4 source-hit limits, ordering, and result shape.
- Full `pytest -q`: collection stopped with 4 collection errors because `legal_bot/data/iran/laws.json` is absent from both Batch 3 and Batch 4 packages.
- Broad suite excluding those four collection-blocked test modules:
  - Batch 3 baseline: 334 passed, 53 failed.
  - Batch 4: 338 passed, 53 failed.
  - Failure-name comparison: 0 new failures, 0 resolved failures; all 53 failures are identical between the two packages.
  - Of the 53 failures, 52 are caused by the missing `laws.json`; one pre-existing citation test fails with `AssertionError: assert None == 'قانون مدنی'` in both versions.

This establishes no observed regression from Batch 4 in the executable test set. It is not a full production sign-off because the legal corpus file is missing and the same baseline failures remain.

## Code line count (raw physical lines)

Counted source files with extensions `.py`, `.js`, `.css`, `.html`; generated caches excluded.

| Category | Files | Lines | Non-empty lines |
|---|---:|---:|---:|
| Production Python (project root + `legal_bot`) | 98 | 31,622 | 28,298 |
| Python tests (`tests`) | 79 | 6,505 | 5,342 |
| Mini App / web source (JS, CSS, HTML) | 3 | 2,643 | 2,534 |
| **Total source + tests** | **180** | **40,770** | **36,174** |

Note: the totals above count source and tests, not Markdown reports, JSON data, configuration, or other documentation. Physical line counts may vary by one if a tool counts a missing final newline differently.

## Conclusion

No regression was detected relative to Batch 3. Batch 4 adds 47 physical lines overall (46-line shared helper module plus the 47-line test file, with one report file excluded from code counts) while removing duplicate helper definitions from the 15 consumer modules. The next safe step is to repair/restore the authentic `laws.json` asset from the project's trusted source, then rerun the complete suite before any further refactor.
