# Stage 6 — Drafting

## Goal
Turn the existing case-grounded drafting pipeline into a complete Mini App vertical slice while keeping the Core workflow authoritative.

## Delivered
- Case workspace now exposes a dedicated Drafting card.
- User selects a brief type and triggers one drafting action.
- Existing V150 preflight remains the gate for required/conflicting case information.
- Incomplete cases stop before artifact creation and return a stable nullable `artifact` contract.
- Successful drafting persists an immutable, versioned `drafting_artifacts` record.
- Draft history is exposed through:
  - GET `/api/v1/cases/{id}/drafts`
  - GET `/api/v1/cases/{id}/drafts/{artifact_id}`
- Existing POST `/api/v1/cases/{id}/draft` is retained and now has a complete Mini App consumer.
- Draft status distinguishes `READY_FOR_REVIEW` from `NEEDS_LAWYER_REVIEW`.
- UI explicitly marks drafts as requiring human review before legal use.
- Artifact table initialization is part of API server startup.
- Existing Core drafting engines and consistency gate remain the source of truth.

## Validation
- 41 tests passed.
- Preflight: PASS.
- Python compile: PASS.
- JavaScript syntax: PASS.
- API route/artifact initialization contract: PASS.

## Notes
A direct local TCP smoke attempt in the sandbox could not bind/connect reliably, so API route coverage was validated through the handler contract plus the full service-level test suite rather than claiming a network smoke result.
