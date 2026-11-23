# MACHINA Growth Batch 21 — Stage 5 Final QA

Date: 2026-10-31
Base: Batch 21 Stage 4 — Case Instrument Panel UI

## Scope

Final static, automated, privacy, and regression QA for the case dashboard aggregator, deterministic alert prioritization, and Pagani/steampunk-inspired instrument panel. This stage makes two small hardening corrections discovered during review; it does not introduce a new feature or refactor unrelated systems.

## Corrections made

1. **Dashboard draft metadata minimization:** the dashboard's `drafting.latest` preview now exposes only `id`, `version_no`, `status`, `brief_type`, `created_at`, and `updated_at`. Full draft text and serialized output are excluded from the dashboard summary. The existing top-level workspace drafting contract was left unchanged for backward compatibility.
2. **Main gauge calibration:** corrected the main dial's 11 tick marks to follow the same upper semicircle as the needle and scale (0 at left, 50 at top, 100 at right).
3. **Keyboard accessibility:** added visible `:focus-visible` styling for mini-gauge and alert buttons.

## Automated verification

- `pytest -q`: **323 passed**
- `node --check miniapp/app.js`: PASS
- `python -m compileall -q legal_bot tests`: PASS
- `python preflight.py`: PASS
- Responsive CSS presence check: PASS
- Reduced-motion CSS presence check: PASS
- Dashboard draft-body exclusion regression test: PASS
- Main gauge tick alignment regression test: PASS
- Instrument keyboard-focus regression test: PASS

## Security and correctness checks covered

- Case workspace access is owner-scoped; cross-user case access is rejected.
- Dashboard child data queries are scoped by authenticated user and case ID.
- Lawyer note body, date source text, and case-event details are not included in dashboard summary.
- Dashboard draft preview excludes full draft body and output payload.
- Dashboard open does not invoke AI providers; AI metadata explicitly marks `auto_invoked: false`.
- Lightweight workspace mode does not invoke deep intelligence engines.
- Alerts are deterministic, sorted by score/date/stable ID, and capped at 20.
- Extracted dates are explicitly not treated as validated statutory deadlines; evidence gaps and extracted conflicts remain review signals.

## Not claimed / remaining device validation

- No real Telegram WebView or physical-device visual test was run in this environment.
- No concurrent-user or production load test was run.
- Browser rendering, touch target feel, and exact visual calibration should be checked in Telegram on at least one narrow Android device and one wider viewport before release.

## Result

**Automated QA: PASS.** Batch 21 stages 1–5 are complete in the packaged source. Device/WebView acceptance remains a separate manual release check.
