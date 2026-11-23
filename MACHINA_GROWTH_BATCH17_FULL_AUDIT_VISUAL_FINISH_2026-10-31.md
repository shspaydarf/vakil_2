# MACHINA Growth Batch 17 — Full Integration Audit & Classic Tools Visual Finish

Date: 2026-10-31
Base: Growth Batch 16 — Service Profile Mini App

## Audit scope
- Reviewed the current Telegram bot main menu, registered callback families, Mini App home navigation, classic-tools hub, AI submenu, and API dispatcher.
- Cross-checked the newly integrated bot workflows against the Mini App calls and API handlers.
- Reviewed user ownership checks for clients, cases, referrals, service profiles, important dates, and private lawyer libraries/workflows.
- Re-ran the complete automated suite and syntax/preflight checks.

## Integration inventory

| Existing lawyer workflow | Mini App destination | Audit result |
|---|---|---|
| Legal search and glossary | Classic tools → Legal search | Connected |
| Case cabinet, case workspace, documents, drafts, reviews, evidence, timeline, notes, tasks | Case vault/workspace | Connected |
| AI question, analysis, issue/evidence review, drafting/review | AI submenu and selected case | Connected |
| AI contract playbooks and AI workflow templates | AI submenu only | Connected; correct placement |
| Client records and case linking | Classic tools → Clients | Connected |
| Calculators and conversion/date helpers | Classic tools → Calculators | Connected |
| Local legal guides and tax-screen OCR | Classic tools → Guides | Connected |
| Guided local decision trees | Classic tools → Guided trees | Connected |
| Lawyer referrals and received matches | Classic tools → Referrals | Connected |
| Service profile, license-photo submission, admin review callback | Classic tools → My service profiles | Connected in API/UI; live Telegram delivery not tested |
| Important case dates and reminders | Calendar | Connected |
| Subscription information and receipt submission | Account/subscription | Connected; admin approval remains manual |
| Support and feedback | Help/support | Connected |
| Recent activity, saved documents, work-product library, personal library, workflows, review tables | Home/AI workspace | Connected |
| Lawyer preference capture/preview | Account preference form | Connected as a temporary preview only; no persistent memory or AI injection yet |

## Deliberately excluded
- Student quiz and essay practice (`🎓 آزمون دانشجویی`) remains Telegram-bot-only because it is outside the lawyer Mini App scope.
- Admin-only approval/rejection and payment-review controls remain in Telegram admin workflows.
- Telegram main-menu callbacks that are navigation aliases or obsolete compatibility paths are not duplicated as separate Mini App pages.

## Issues found and corrected
1. **Service submission notification failure could invite duplicate submissions.** The service record was already saved before admin notification; returning HTTP 502 could make the client retry and create a duplicate. The API now returns HTTP 202 with `notification_sent:false` and an explicit no-retry/support message when the record is saved but admin notification fails. Successful notifications retain 201/200 responses.
2. **New classic-tools UI looked more generic than the previously designed dashboard.** Added a CSS-only metallic/champagne finish to the classic launcher, tool cards, forms, result cards, service status chips, and controls. Kept the light green/paper palette, readable dark text, subtle interaction, and reduced-motion support. No image assets or external dependencies added.

## Ownership and privacy checks
- Service list is queried by authenticated Telegram user ID.
- Service update checks record ownership before reading multipart upload data or contacting Telegram.
- Service delete uses owner-scoped DB update and soft-deletes.
- License photo is forwarded to admin Telegram accounts and is not stored in the service-listing row or public profile.
- Service edits return the record to pending review.
- Client/case/referral/calendar/library/workflow ownership checks remain covered by existing tests and implementation.

## Verification
- Full pytest suite: **290 passed**.
- `node --check miniapp/app.js`: PASS.
- `python -m compileall -q legal_bot`: PASS.
- `python preflight.py`: PASS.
- ZIP integrity: checked after packaging.

## Not live-tested
- Telegram WebView rendering on a physical device.
- Real license-photo upload, admin notification, or admin approval callback in a deployed Telegram bot.
- Real subscription receipt submission/review.
- Two-account production isolation, deployment proxy/TLS/initData configuration, OCR production corpus, AI-provider calls, or concurrent-user load.

## Conclusion
The reviewed lawyer-facing workflows are represented in the Mini App. The student quiz/essay feature is the one deliberate functional exclusion. Preference capture is connected only at its documented temporary-preview stage, not persistent lawyer memory. This audit is code/test based and does not certify live deployment or production readiness.
