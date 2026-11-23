# MACHINA — Lawyer Memory & Preferences | Stage 2 of 6

**Status:** Implemented as a stateless capture and proposal experience. Persistent profile storage is intentionally deferred to Stage 3.

## Delivered

- Added a seven-category preference form in the Mini App, accessible from the account/settings panel.
- Added optional fields for professional context, writing style, legal analysis, citations/sources, output formats, document review, and assistant interaction.
- Empty fields remain unset; the UI does not silently assign system defaults as lawyer preferences.
- Added tri-state controls for yes/no preferences so an untouched value is distinct from an explicit `false`.
- Added controlled feedback signals that produce deterministic preference proposals.
- Every proposal is marked `ai_suggestion`, requires an explicit lawyer action to apply to the draft form, and is never automatically persisted.
- Added authenticated API routes:
  - `GET /api/v1/lawyer-preferences/schema`
  - `POST /api/v1/lawyer-preferences/suggest`
  - `POST /api/v1/lawyer-preferences/preview`
- Added server-side allowlist validation, choice validation, multi-select limits, and free-text length limits.
- Added explicit preview and lawyer-confirmed preview states.
- Added privacy warnings not to enter client names, case facts, case identifiers, documents, or privileged communications.
- Preserved the boundary: the feature applies to the Mini App/digital AI environment only; no Gramophone/classic menu behavior was changed.

## Persistence boundary

No database table, migration, or persistent profile write was added in Stage 2. The preview endpoint returns `persisted: false`, including after lawyer confirmation. Durable per-lawyer storage, read/edit/deactivate/delete, audit history, export, and isolation enforcement are Stage 3 scope.

## Feedback behavior

Suggestions are generated only from a controlled feedback choice (for example, “too long” → propose concise detail level). Free-text case material is not parsed to infer permanent preferences. The proposal can only be copied into the current form draft by the lawyer.

## Validation

- Existing baseline: 172 tests passed before changes.
- Stage 2 adds tests for schema shape, optional/unset values, validation, suggestion confirmation, stateless preview, API behavior, and Mini App wiring.
- Python compilation and JavaScript syntax checks are part of release validation.

## Deferred

- Stage 3: secure persistent profile storage, owner scoping, access control, view/edit/deactivate/delete, audit history.
- Stage 4: applying confirmed preferences to AI capabilities.
- Stage 5: feedback loop, preference conflict handling, versioning and rollback.
- Stage 6: final Mini App integration polish, security/regression testing and release.
