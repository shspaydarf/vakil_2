# MACHINA — Stage 2 Audit: Ancillary Tools & Playbooks

Date: 2026-10-30  
Base: `LegalBot_MACHINA_Audit_Stage2_Lawyer_Memory_Preferences_2026-10-30.zip`

## Scope
Audited the Telegram bot handlers/callback registration, Mini App home tool cards and JavaScript routing, API route surface, ancillary tool modules, and built-in contract Playbooks. This was a source-level and automated-test audit; no live Telegram session, production database, external AI provider, or real-device visual session was exercised.

## Connection map and status

| Feature | Current user surface | Backend path | Stage 2 status |
|---|---|---|---|
| Mini App: legal question | Mini App home card; user selects a case | Mini App case workspace/API | Connected in Mini App; case-bound |
| Mini App: case analysis | Mini App home card; user selects a case | Mini App case workspace/API | Connected in Mini App; case-bound |
| Mini App: evidence/issues | Mini App home card; user selects a case | Mini App case workspace/API | Connected in Mini App; case-bound |
| Mini App: drafting/review | Mini App home card; user selects a case | Mini App case workspace/API | Connected in Mini App; case-bound |
| Contract Playbooks (construction, lease, sale) | Telegram inline keyboard from AI contract review | `aicontract:<case_id>[:<playbook_id>]` → `ai_contract_review_cb` → `build_playbook_checklist` → `review_contract_risks` | Working Telegram-bot flow; no Mini App Playbook screen or API route found |
| Calculators / calendar / deadline tools | Telegram inline keyboards | `calc:*` callback handlers and local calculator/date modules | Telegram-bot-only; no Mini App route/card found |
| Tax helper and tax-screen guide | Telegram inline keyboards; image upload for screen explanation | `tax*` callback flow and local guide builders | Telegram-bot-only; no Mini App route/card found |
| Dispute council / peace court guide | Telegram inline keyboards | `shora:*` callback flow and guide builder | Telegram-bot-only; no Mini App route/card found |
| Lease guide | Telegram inline keyboards | `ejare:*` callback flow and guide builder | Telegram-bot-only; no Mini App route/card found |
| Cheque guide | Telegram inline keyboards | `check:*` callback flow and guide builder | Telegram-bot-only; no Mini App route/card found |
| Quiz / educational exam | Telegram inline keyboards | `quiz:*` callback flow and question bank | Telegram-bot-only; not surfaced in Mini App |

## Playbooks: findings

- Three static built-in Playbooks exist: construction, lease, and sale.
- The picker is opened before any AI request or quota reservation.
- The chosen case must belong to the Telegram user and must not be archived.
- Review uses extracted case text; it does not directly submit original image/PDF files through this handler. Missing extracted text stops the flow.
- The handler checks both AI enablement and external-data consent before reserving quota. On review failure, the reservation is refunded; on success, it is committed.
- The report is returned as Telegram text and a generated PDF. PDF failure leaves the text report available and shows a warning.
- The callback pattern in `main.py` accepts the three supported lowercase/underscore Playbook IDs.
- Existing Playbook tests cover the three definitions, non-empty/unique criteria, normalized checklist, unknown IDs, and detached copies.
- Playbooks remain static; no user-defined templates, persistent review history, saved criterion annotations, Mini App interface, or per-lawyer preference integration is present.
- Important boundary: absence of a validated finding must not be interpreted as compliance or absence of risk. Existing Playbook reports explicitly state this limitation.

## Ancillary tools: findings

- The ancillary flows are implemented as Telegram callback conversations using `context.user_data` for temporary multi-step state (e.g. tax, council, lease and cheque flows).
- The calculator/date functions are primarily deterministic/local, but some values are explicitly approximate or dependent on official annual rates/tariffs. Their existing disclaimers should remain visible.
- No matching Mini App home cards or Mini App API endpoints were found for these ancillary flows in this source snapshot. They must not be described as Mini App-connected merely because their Python modules exist.
- No code was changed in this audit: there was no low-risk defect established that justified modifying these established bot flows without live interaction tests. In particular, no feature was silently removed or moved.

## UI consistency

- Mini App currently exposes four primary tool cards: legal question, case analysis, evidence/issues, and drafting/review.
- Those cards share the existing Mini App tile system and route through a case picker before opening the selected case workspace.
- Telegram-only ancillary tools and Playbook picker use Telegram inline keyboards, so Mini App visual consistency cannot be claimed for them. A future Mini App port would need native Mini App screens and API routes, not just visual button copies.

## Risks / follow-up

1. Playbook reports are not saved as case artifacts in the reviewed handler; they are sent to Telegram as text/PDF. If durable case history is required, implement a separate, permission-checked artifact-save flow in a later stage.
2. Playbooks are not currently exposed in Mini App. Do not assume the four Mini App tiles include contract Playbooks.
3. Ancillary tools are bot-only in this snapshot. Any future Mini App integration should be scoped individually, with exact input validation, server-side ownership checks, and parity tests.
4. The Telegram conversational flows use in-memory `context.user_data`; persistence across process restarts should not be assumed.
5. Live external AI behavior, actual Telegram callback execution, PDF appearance on target devices, and multi-user isolation/load were not tested here. These belong to later audit stages.

## Verification

- `pytest -q`: **204 passed**.
- Python compile check: completed successfully.
- Mini App JavaScript syntax check: completed successfully.
- `preflight.py`: completed successfully.
- ZIP integrity check: passed.

## Conclusion

The four primary Mini App case tools are connected to the Mini App case workspace. Contract Playbooks are a functional Telegram-bot AI workflow, not a Mini App feature. Calculators, calendar, tax, dispute-council, lease, cheque and quiz flows are Telegram-bot-only in this version. No code change was warranted in this audit; the main outcome is a verified feature-surface map and a list of honest integration boundaries for the next stages.
