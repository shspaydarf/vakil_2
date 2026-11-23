# LegalBot — Project Health Check

Date: 2026-10-06
Baseline: Stage 8 Production Hardened

## Overall status

The project is a substantial working Telegram bot + Mini App adapter, not a UI-only prototype.
The current codebase contains the case workflow, document ingestion, chronology, evidence mapping,
legal intelligence, case-grounded AI, drafting artifacts, Telegram handlers, local legal corpus,
credit/entitlement infrastructure, durable storage and production hardening.

Validation after this audit:
- pytest: 48 passed
- preflight: PASS
- Python syntax: PASS
- Mini App JavaScript syntax: PASS
- Local API lifecycle checks are covered by existing API tests.

## Important fixes made in this audit

1. Restored Stage 1 Case Management UI behavior that had regressed from the Stage 7 Mini App file:
   - search
   - active/archive tabs
   - create modal with stage/priority/next action
   - edit case
   - archive/restore
   - permanent delete
2. Fixed Mini App AI response handling. The API helper already unwraps `data`; the UI was incorrectly
   reading `.data` a second time.
3. Added an nginx static Mini App service and API reverse proxy to production compose so `MINIAPP_URL`
   can point to the same deployment instead of requiring an undocumented separate static host.
4. Added regression tests for the Mini App case-management/API contract and compose static hosting.
5. Removed generated runtime artifacts from the release package.

## Current architecture

Telegram Bot / Mini App
→ HTTP API
→ ProductCaseService / Core Services
→ repositories / engines
→ SQLite + durable storage

The Mini App is still an adapter. Core services remain authoritative for business and legal workflow rules.

## What is genuinely implemented

### Case Management
- create/update/list/search
- active vs archived
- archive/restore/delete
- stage, priority, next action
- ownership validation

### Documents
- multi-file upload
- PDF/DOCX/TXT/images
- extraction/OCR path
- durable storage
- preview metadata
- delete
- atomic upload batch behavior

### Evidence + Timeline
- extracted events
- source/page provenance
- chronology conflicts
- claim/evidence matrix
- support/contradiction/gap states

### Legal Intelligence
- risk/confidence summary
- findings
- evidence gaps
- recommended actions
- open questions
- deterministic/local analysis layer

### AI in Case
- case-grounded context modes
- metered entitlement lifecycle
- durable AI history
- provider failure refund
- archived-case rejection
- external processing opt-in configuration

### Drafting
- preflight gate
- versioned immutable artifacts
- human-review status
- archived-case rejection
- serialized version allocation

### Telegram integration
- Mini App launcher
- case-specific launch URL
- Telegram initData authentication
- legacy bot handlers remain intact

### Production hardening
- production config guards
- rate limiting
- security headers
- CSP
- upload/body limits
- environment-driven storage/DB/backups
- Dockerfile
- nginx + compose deployment path

## What is still missing / incomplete

### P0 — required before calling it production

1. Real deployment:
   - public HTTPS domain
   - TLS/reverse proxy
   - real BOT_TOKEN
   - real Mini App URL
   - production environment/secrets
2. Real Telegram end-to-end acceptance test.
3. Real AI provider acceptance test with the intended model/key and cost limits.
4. Backup scheduling/restore drill in the real host environment.
5. Operational monitoring/alerting and log rotation outside the application process.

### P1 — important product gaps

1. Mini App account/settings page is still a placeholder.
2. Subscription/credit UI is not integrated into Mini App even though Core supports it.
3. Tasks/reminders/next-step management are not first-class Mini App views.
4. Lawyer notes are not exposed as a Mini App workflow.
5. Authority/law/source views are not fully exposed in the Mini App workspace.
6. Draft export to Word/PDF is not exposed by the Stage 6 Mini App slice.
7. Draft version compare/use workflow is not exposed in Mini App.
8. Legacy Telegram case menu still contains placeholder callbacks for adding photo/text and version comparison.
9. User/account/support/feedback flows are still primarily Telegram-side.
10. Mini App does not yet provide a polished global notification/error center.

### P2 — hardening / scale

1. Rate limiting is in-memory and therefore per-process; production multi-instance deployment needs shared limiting.
2. SQLite is suitable for a small deployment but should be evaluated before horizontal scaling.
3. Persistent backup retention/verification needs an external scheduled mechanism.
4. No full observability stack (metrics/traces/centralized logs) is bundled.
5. No CI pipeline is included in the artifact.
6. No automated browser/E2E test suite for Telegram Mini App UI is included.

## Important interpretation

The project is currently best described as:

**Production-hardened candidate / single-instance deployable application**,
not yet a fully operated production SaaS.

The main remaining risk is no longer the basic Case→Document→Evidence→AI→Draft architecture.
The main remaining work is deployment, real Telegram/provider acceptance, and product-surface completion.
