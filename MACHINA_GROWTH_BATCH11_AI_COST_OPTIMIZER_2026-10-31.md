# MACHINA Growth Batch 11 — AI Cost Optimizer

Date: 2026-10-31
Base: Growth Batch 10 — AI Usage Metering

## Scope

This batch adds a conservative, deterministic prompt-format optimizer and extends the privacy-minimal usage ledger. It does not change legal reasoning, source selection, output limits, AI model choice, external-data consent, or quota enforcement.

## Changes

- Added `legal_bot/ai_optimizer.py`.
- Shared AI call path now removes only formatting noise from text prompt content: trailing spaces and runs of three-or-more blank lines. It preserves paragraph boundaries, wording, punctuation, numbers, JSON content, page markers, message order, and non-text/multimodal blocks.
- Added a rough character-based prompt-token estimate for planning only. It is explicitly not used for billing, quota decisions, or claims of actual token savings.
- Usage ledger now records aggregate prompt character count, estimated prompt tokens, and formatting characters removed. It still does not store prompts, completions, user IDs, case IDs, file names, or document contents.
- Existing databases are upgraded in place with additive SQLite columns.
- Admin usage report now includes optimizer metrics, a note distinguishing estimates from provider-reported usage, and cautious feature-level review hints.
- No Mini App navigation changes: this is an internal optimization/measurement layer, not a new user-facing AI feature.

## Safety boundaries

- No semantic summarization or deletion of legal facts is performed by this optimizer.
- No cross-user or cross-case AI response cache was added.
- No request batching or output truncation was introduced, because those can alter legal coverage or quality.
- Provider-reported token usage remains authoritative. The character-based estimate is approximate, especially for Persian and mixed-script text.
- AI requests remain subject to existing explicit external-data consent and AI enablement checks.

## Verification

- Full pytest suite: **255 passed**.
- `node --check miniapp/app.js`: PASS.
- `python -m compileall -q legal_bot`: PASS.
- `python preflight.py`: PASS.
- ZIP integrity checked after packaging.

## Not performed

- No live request to the configured AI provider was made.
- No real invoice/price validation was performed.
- No live Telegram/browser end-to-end test or concurrent load test was performed.

## Next useful step

After deployment with real provider credentials, compare provider-reported prompt tokens before/after this formatting-only optimizer over a representative sample. Only then decide whether any feature-specific prompt redesign is justified. Any semantic compression should be separately tested for legal fact/provenance preservation and explicitly approved.
