# MACHINA Growth Batch 15 — Bot-to-Mini App Integration

Date: 2026-10-31
Base: Growth Batch 14 — Hybrid Retrieval

## Objective

Expose lawyer-facing workflows that already existed in the Telegram bot but were not reachable from the Mini App. This batch prioritizes connection and reuse of existing engines over improving their underlying legal quality. AI-dependent contract playbooks remain inside the AI submenu; deterministic tools remain outside it.

## Mini App additions

A new home launcher, **ابزارها و خدمات حقوقی**, opens a classic-tools hub containing:

1. **Unified legal search** — calls the existing law search and glossary lookup functions; source detail and related-source view are available. Search results are discovery aids, not validation of current legal force.
2. **Client management** — authenticated per-user list, search, create, edit, delete, detail, and case linking. The existing client database functions are reused.
3. **Legal calculators** — shared calculator reference data is moved to `legal_bot/calculator_data.py`, so bot and API use the same annual mahr indices and provisional-year markers. Exposed calculators include mahr, full diya and selected head-wound/skin-color percentages, delay-damage with user-entered indices, court fee, financial-case lawyer fee, deadline addition, quick percentage, toman/rial conversion, installment split, date difference, Jalali/Gregorian conversion, Iran-local current date, and Article 702 fine estimate. Existing calculation formulas are reused; the UI labels limits and provisional values.
4. **Guides** — existing local guide builders for cheque/promissory note, lease/eviction, family/mahr, Peace Court, and tax guidance.
5. **Tax-screen OCR** — image upload from Mini App to the existing local OCR pipeline and tax-screen guide builder. This path does not call AI.
6. **Guided case trees** — existing local decision trees for contracts, claims/debts, property, cheques, and leases. State is held server-side, scoped by Telegram user and session token, with a one-hour expiry; document text is not returned to the browser as workflow state.
7. **Referrals** — list the user's own requests and received lawyer matches; create a referral request with explicit consent; accept, decline, or request more information on received matches. Existing DB workflow is reused and Telegram notifications are sent for the same lifecycle events.
8. **Help and support** — short in-app help and authenticated support/bug feedback submission.

## Other connections

- **Important dates:** extracted case dates already shown in the calendar now have an explicit one-day-before reminder toggle. The existing Telegram reminder scheduler delivers the notification; no legal deadline is inferred by the Mini App.
- **Subscription:** account view now exposes subscription terms and card-to-card details and accepts receipt images. Receipt requests are created in the existing payment-review table and sent to configured admins for manual review. Uploading a receipt does not activate a subscription; admin approval remains required.
- **AI contract playbooks:** existing contract playbooks (construction, lease, sale) are exposed inside the AI submenu only. The API checks AI configuration, external-data consent, case ownership, extracted text, and AI entitlement before making a request. Failed calls refund the reservation.

## API routes added

- `GET /api/v1/legal-search?q=&limit=`
- `GET /api/v1/legal-search/source?id=`
- `GET /api/v1/clients`, `GET /api/v1/clients/{id}`
- `POST /api/v1/clients`, `PATCH /api/v1/clients/{id}`, `DELETE /api/v1/clients/{id}`
- `POST /api/v1/clients/{id}/cases/{case_id}`
- `GET /api/v1/calculators`, `POST /api/v1/calculators/run`
- `GET /api/v1/guides/catalog`, `POST /api/v1/guides/{kind}`
- `POST /api/v1/tax/screen`
- `POST /api/v1/guided-trees/{kind}/start`, `POST /api/v1/guided-trees/{kind}/step`
- `GET /api/v1/important-dates`, `POST /api/v1/important-dates/{id}/reminder`
- `GET /api/v1/referrals`, `POST /api/v1/referrals`, `POST /api/v1/referrals/matches/{id}`
- `POST /api/v1/feedback`
- `GET /api/v1/subscription-info`, `POST /api/v1/subscription-receipts`
- `GET /api/v1/contract-playbooks`, `POST /api/v1/cases/{id}/contract-review`

All routes use Telegram-authenticated identity; client, case, date, and referral records are owner-scoped. No client-supplied user ID is accepted as the authority for data access.

## Deliberately not moved

- Student quiz and essay-practice tools are not included in the lawyer Mini App.
- Admin-only approval/rejection tools remain in the Telegram admin workflow.
- Lawyer service-listing profile creation/editing and license-photo submission are still bot-side; this is the next remaining lawyer-facing connection candidate.
- No underlying guide, calculator, OCR, or retrieval accuracy upgrade is claimed in this batch. Connection is not a quality certification.

## Verification

- Full automated test suite: **286 passed**
- `node --check miniapp/app.js`: PASS
- `python -m compileall -q legal_bot`: PASS
- `python preflight.py`: PASS
- ZIP integrity: checked at packaging time

No live Telegram WebView session, real payment submission, real AI contract review, OCR against a production image corpus, or concurrent-user load test was run. Telegram delivery and payment-review behavior are covered by mocked API tests only.
