# MACHINA — Lawyer Memory & Preferences | Stage 1 of 6

**Status:** Design specification (no application code or database changes)  
**Scope:** Digital/AI menu only. The Gramophone/classic section is explicitly out of scope.

## 1. Objective
Define a per-lawyer profile describing preferred working style and output behavior. The profile is a set of explicit preferences, not a source of legal truth and not a substitute for professional judgment.

## 2. Profile categories and fields

### A. Professional context
- `practice_areas`: multi-select; optional; examples: contracts, property, family, criminal, commercial, labor, administrative, other.
- `jurisdiction`: optional; country/region and, where relevant, legal system.
- `professional_role`: optional; lawyer, in-house counsel, legal researcher, other.
- `practice_context_note`: optional free text, with a short length limit; must not contain client/case secrets.

### B. Writing style
- `tone`: formal / neutral / plain-language / persuasive.
- `detail_level`: concise / balanced / detailed.
- `legal_language`: technical / accessible / mixed.
- `preferred_language`: optional language code.
- `style_note`: optional free text.

### C. Legal analysis method
- `analysis_structure`: issue-rule-application-conclusion / step-by-step / executive-first / custom.
- `risk_focus`: low / balanced / high; controls emphasis, not risk truth or legal conclusion.
- `counterargument_review`: enabled / disabled (default enabled when analyzing legal positions).
- `uncertainty_handling`: explicitly flag unknowns and assumptions (default enabled).

### D. Legal citations and sources
- `citation_density`: comprehensive / relevant-only / concise.
- `citation_format`: inline / footnotes / endnotes / jurisdiction-specific.
- `source_priority`: configurable ordered list, e.g. legislation, binding precedent, persuasive precedent, official guidance, secondary sources.
- `citation_verification`: request verifiable source details where available (default enabled).
- A preference can never authorize fabricated citations or imply that a source was checked when it was not.

### E. Output formats
- `default_output_types`: memo / pleading / petition / contract / clause review / comparison table / executive summary / other.
- `heading_style`: numbered / descriptive / minimal.
- `include_executive_summary`: yes / no.
- `include_action_items`: yes / no.
- `format_note`: optional free text.

### F. Document-review preferences
- `review_focus`: obligations / deadlines / payment / liability / termination / dispute resolution / confidentiality / data protection / other.
- `comparison_mode`: summarize differences / identify potential conflicts / clause-by-clause comparison.
- `evidence_display`: quote supporting passage and identify document/page when available (default enabled).
- `missing_information_behavior`: ask questions / list assumptions / both (default both).

### G. Assistant interaction
- `clarification_behavior`: ask_before_material_assumptions / proceed_with_marked_assumptions / balanced.
- `proactivity`: conservative / balanced / proactive.
- `explanation_level`: brief / normal / detailed.
- `suggest_next_steps`: yes / no.

## 3. Required versus optional

**Required to create a profile:** none beyond authenticated lawyer identity supplied by the application. A profile may exist with all preference fields unset.  
**Optional:** all preference fields above.  
**Defaults:** use neutral system defaults, clearly distinguished from lawyer-confirmed preferences. Never silently treat an unset value as a user preference.

## 4. Preference provenance and lifecycle
Every preference should eventually carry metadata in implementation:
- origin: `lawyer_entered`, `lawyer_confirmed_suggestion`, or `system_default`;
- created/updated timestamps;
- version and active status;
- optional note explaining the preference.

Stage 1 defines these metadata requirements only; it does not introduce a database schema.

## 5. Privacy and isolation rules
1. One lawyer's profile must never be visible to another lawyer unless an explicitly authorized organization-level sharing feature is designed later.
2. Do not place client names, case facts, uploaded documents, privileged communications, or case identifiers in this preference profile.
3. Case-specific instructions belong to the case context, not the persistent lawyer profile.
4. Only explicitly confirmed preferences may be applied as learned preferences. The AI may suggest a preference but must not persist it automatically.
5. The lawyer must be able to inspect, edit, deactivate, and delete preferences in a later stage.
6. Applying a preference may change presentation and workflow behavior; it must not weaken access controls, source verification, safety checks, or legal review.

## 6. Application boundary
The profile is intended only for MACHINA's digital/AI capabilities, such as AI drafting, contract review, multi-document analysis, and legal search presentation. No changes are authorized to the Gramophone/classic menu.

## 7. Acceptance criteria for Stage 1
- Seven categories and their fields are defined.
- Required/optional behavior and neutral defaults are explicit.
- Unset values are distinguishable from confirmed preferences.
- Preference provenance is specified.
- Lawyer isolation and case-data separation are explicit.
- No DB schema, migration, API, UI, or application code is changed in this stage.

## 8. Deferred to later stages
- Stage 2: preference capture UI and explicit confirmation flow.
- Stage 3: secure storage, access control, editing/deletion, and auditability design/implementation.
- Stage 4: applying preferences to AI features.
- Stage 5: feedback-based suggestions and controlled updates.
- Stage 6: Mini App integration, isolation/security tests, regression tests, and delivery.

## 9. Open design decisions for owner approval
- Final practice-area list and jurisdiction model.
- Whether profiles may be shared within a law firm (default: no sharing).
- Exact citation styles supported for the target jurisdiction(s).
- Whether organization administrators can manage defaults (default: they cannot read or change personal preferences).
