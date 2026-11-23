# LegalBot Stage 5 — AI Inside Case

## Scope
AI is now a first-class case workspace action. The Mini App sends only the question and
a context mode; the product service builds the canonical case context from Case,
Documents, Timeline, Issues, Evidence and Legal Intelligence.

## Implemented
- `ProductCaseService.ask_ai(...)`
- Metered entitlement lifecycle: reserve -> external AI call -> commit/refund
- Archived cases reject AI questions
- Bounded case context to control cost/latency
- Context modes: `full`, `intelligence`, `documents`
- Durable case AI history
- API: `POST /api/v1/cases/{id}/ai`
- Existing `GET /api/v1/cases/{id}/ai-history` retained
- Mini App Case AI panel with mode selector, question form, answer and history
- Human-review warning preserved
- No automatic AI invocation when opening a case

## Validation
- pytest: 38 passed
- preflight: PASS
- Python compile: PASS
- JavaScript syntax: PASS

## Important behavior
- AI usage is charged only after a successful provider call.
- Provider failure refunds the reservation.
- Archived cases cannot use case AI.
- The Mini App does not implement business rules; the Core/Product service remains canonical.
