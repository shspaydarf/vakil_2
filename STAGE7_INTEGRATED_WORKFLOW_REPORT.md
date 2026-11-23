# Stage 7 — Integrated Workflow + Telegram UX

## Scope

Stage 7 integrates the existing Case, Documents, Timeline, Evidence, Intelligence, AI and Drafting capabilities into one Mini App workspace flow and adds a Telegram launch bridge.

## Delivered

- Telegram-configurable Mini App launch URL via `MINIAPP_URL`.
- Reply-keyboard Web App launcher for the case area.
- Optional case-specific launch: `MINIAPP_URL?case=<case_id>`.
- Mini App reads the `case` query parameter and opens that owned case after Telegram authentication.
- Case Workspace now exposes the next action prominently and provides quick actions.
- Documents are now a first-class Workspace action:
  - list documents
  - multi-file upload through the existing Core/API path
  - delete document
  - refresh the full case context after upload
- Existing AI, Timeline, Evidence, Legal Intelligence and Drafting views remain on the same Workspace context.
- No legal/business rules were moved into the frontend.

## Architecture

`Telegram → Mini App launcher → Telegram initData → HTTP API → ProductCaseService / Core → Repository / DB / Storage`

## Validation

- Full regression suite: **43 passed**
- Preflight: **PASS**
- Python compile: **PASS**
- JavaScript syntax: **PASS**
- Static Stage 7 integration checks: **PASS**

The sandbox does not have `python-telegram-bot` installed, so a live Telegram dispatcher import/build check could not be executed here. This is an environment limitation; syntax and project tests remain green.

## Configuration

Set `MINIAPP_URL` to the HTTPS public URL where `miniapp/index.html` is served. Keep Telegram `initData` authentication enabled in production; do not enable the development auth escape hatch in production.
