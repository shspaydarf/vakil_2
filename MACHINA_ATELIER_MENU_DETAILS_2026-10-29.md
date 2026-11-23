# MACHINA Atelier — Menu Details Update

## Summary
Added small decorative service hatches to dynamically rendered workspace, legal-tool, and account-dialog headers. The hatches reveal a short, context-sensitive atelier note, copper/steel visual details, and a tiny animation. Three quick taps on the hatch trigger a decorative compass spin and toast.

## Scope and safeguards
- Updated only `miniapp/app.js` and `miniapp/styles.css`, plus this report.
- No changes to API contracts, database, case workflows, legal analysis, law JSON, or operational status.
- All notes explicitly describe effects as decorative and avoid claiming that documents, tasks, account data, or legal analysis were changed.
- Uses event delegation and MutationObservers to support pages rendered dynamically.
- Includes keyboard-focus styling inherited from existing controls, button labels/expanded state, small-screen adjustments, and `prefers-reduced-motion` handling.
- No images, external fonts, or dependencies added.

## Checks performed
- `node --check miniapp/app.js`: PASS
- `python -m compileall -q legal_bot`: PASS
- `python preflight.py`: PASS
- `pytest -q`: 105 passed
- ZIP integrity: checked after packaging

## Not performed
No live Telegram Mini App or physical-device visual test was performed. The checks above do not prove visual behavior in every Telegram WebView or screen size.
