# MACHINA Lawyer Memory — Stage 3.3 Security & Isolation

Date: 2026-10-31

## Scope delivered

- Hardened the existing Stage 3.2 owner-scoped preference repository without adding public API routes or changing Mini App behavior.
- Added privacy screening for common direct identifiers in the four free-text preference fields: Iranian/international mobile-number patterns, 10-digit national-ID-like values, email addresses, and explicit case/client reference labels followed by an identifier.
- Normalized Persian and Arabic-Indic digits before screening.
- Screening is deliberately heuristic: it reduces common accidental disclosures but does not guarantee semantic detection of every secret, address, case identifier, or personal detail.
- Added a SQLite trigger that prevents UPDATE of immutable preference-history snapshots. DELETE remains allowed for the later explicit hard-delete lifecycle and FK cascade.
- Added a SQLite trigger that prevents reassignment of a profile's owner key.
- Added an integrity check: if the current profile version and latest history snapshot disagree, a new save is rejected instead of silently overwriting inconsistent state.
- Preserved owner-scoped SQL predicates on all profile and version-history reads.
- Confirmed the existing API authentication boundary validates Telegram WebApp initData HMAC and rejects tampered user identity. Preference persistence endpoints are intentionally not wired until Stage 3.5; future handlers must pass only the authenticated dispatcher UID and must not accept a body/query `user_id`.
- No case/client tables, case documents, notes, or AI content are read by this module.

## Files changed

- `legal_bot/lawyer_preference_store.py`
- `tests/test_lawyer_preference_security_stage3_3.py`

## Tests added

- Common phone, national-ID-like, email, and labeled case-reference values are rejected from free-text preference fields.
- Persian digits are normalized before checks.
- Ordinary general professional-preference text is accepted.
- History snapshots cannot be updated directly.
- Profile ownership cannot be reassigned.
- Corrupt/missing version history blocks overwrite.
- Profile and history reads remain owner-scoped across two users.
- User deletion cascades profile and history rows.
- Telegram initData helper accepts a correctly signed payload and rejects a tampered identity.

## Validation

- Dedicated preference/security tests: 31 passed.
- Full project suite: 342 passed.
- `python -m compileall -q legal_bot tests`: PASS.
- `node --check miniapp/app.js`: PASS.
- `python preflight.py`: PASS.
- ZIP integrity: PASS.

## Deliberately deferred

- No preference profile GET/PUT/DELETE routes were added in this sub-stage.
- No lifecycle activation/deactivation operations were added.
- No Mini App persistence UI or AI prompt integration was added.
- No production Telegram WebView/device test was performed.

## Security limitation

The identifier filter is a best-effort guard for common accidental disclosures, not a complete DLP system. The Mini App must continue to warn lawyers not to enter case/client details. The future API layer must authenticate every request, derive owner UID only from verified Telegram initData/session, apply rate limits, avoid logging preference text, and map privacy/validation errors safely.
