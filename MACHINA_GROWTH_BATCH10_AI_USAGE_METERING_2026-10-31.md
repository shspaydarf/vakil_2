# MACHINA Growth Batch 10 — AI Usage Metering

Date: 2026-10-31  
Base: Growth Batch 9 — AI Token Optimization

## Objective
Add provider-reported token accounting and per-feature cost visibility without retaining legal prompt/completion content or personal/case identifiers.

## Implemented
- Added `ai_usage_events` ledger: timestamp, feature code, provider/model, prompt/completion/total tokens when provider reports them, latency, status, and a usage-reported flag.
- Instrumented the shared chat-completions call path and the separately implemented vision transcription path.
- Tagged calls by feature: structured extraction, legal Q&A, case summary, text assistance task, verified summary, legal drafting, document consistency review, contract review, and scan transcription.
- Provider token usage is recorded as authoritative only when returned by the provider. Missing usage stays NULL; no fake token counts are generated.
- Optional cost estimates are enabled only when `AI_INPUT_PRICE_PER_1M` and `AI_OUTPUT_PRICE_PER_1M` are configured. `AI_PRICE_CURRENCY` labels the configured unit; it does not fetch or guess prices.
- Added authenticated admin reporting endpoint: `GET /api/v1/admin/ai-usage?days=30`, protected by `AI_USAGE_ADMIN_TOKEN` in `X-AI-Usage-Admin-Token`.
- Reports aggregate by feature and model, include latency/failure counts, and explicitly disclose the privacy model.

## Privacy
The ledger deliberately does not store user IDs, case IDs, file names, prompts, completions, extracted legal text, or API keys. It is installation-wide aggregate accounting, not a per-lawyer billing ledger. Access to the report requires both normal Telegram Mini App authentication and the separate admin token.

## Configuration
- `AI_USAGE_LEDGER_ENABLED=1` (default; set to `0` to disable writes)
- `AI_USAGE_ADMIN_TOKEN=<long-random-secret>` (required to read the admin report)
- `AI_INPUT_PRICE_PER_1M=<provider input price per million tokens>` (optional)
- `AI_OUTPUT_PRICE_PER_1M=<provider output price per million tokens>` (optional)
- `AI_PRICE_CURRENCY=USD` (optional label; defaults to `provider_units`)

Do not set example or guessed pricing. Copy the current rates from the actual provider/model contract and update them when pricing changes.

## Verification
- Full pytest suite: **252 passed**.
- `node --check miniapp/app.js`: passed.
- `python -m compileall -q legal_bot`: passed.
- `python preflight.py`: PASS.
- ZIP integrity check: performed after packaging.

## Limitations
- Provider-reported usage may be absent on some compatible endpoints; those calls are counted but token totals remain unknown.
- Existing calls made before deployment are not backfilled.
- The ledger is aggregate and installation-wide; no individual lawyer usage or chargeback is exposed.
- Cost estimates are only as accurate as the configured provider rates and do not include taxes, discounts, retries billed outside this process, or currency conversion.
- No real provider billing calls, live Telegram/browser tests, or concurrency/load tests were performed.
- This batch exposes a protected JSON admin report endpoint; it does not yet add a visual cost dashboard in the Mini App.
