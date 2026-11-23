# MACHINA Playbooks — Stage 6 PDF Layout

- Improved the contract-review PDF hierarchy with a title/subtitle, section-heading detection, restrained typography, separators, page header/footer, and page numbering.
- Added optional runtime dependencies `arabic-reshaper` and `python-bidi` so Persian/Arabic text is shaped and ordered correctly when installed from requirements.
- Kept a graceful fallback if shaping packages are absent; that fallback does not guarantee correct Persian shaping.
- Added tests for metadata/page chrome and long-report pagination.
- No database schema, law JSON, Gramophone, or external-service behavior changed.

Validation: `pytest -q` — 144 passed in 12.84s.

Not validated: visual rendering on every PDF reader, production installation of the added dependencies, or live Telegram document delivery.
