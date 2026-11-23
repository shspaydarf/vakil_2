# MACHINA Growth Batch 14 — Hybrid Retrieval

Date: 2026-10-31  
Base: Growth Batch 13 — Case Context Cache

## Goal
Improve local selection of relevant case records and document pages before AI context construction, without adding an external AI call or rewriting source text.

## Implemented
- Added `legal_bot/hybrid_retrieval.py`, a dependency-free Persian retrieval scorer.
- Combines normalized exact-token coverage, conservative grammatical suffix handling, term-frequency weighting, and character-trigram similarity for limited OCR/typing variation.
- Persian/Arabic character normalization covers common ي/ی, ك/ک, hamza/alef variants, diacritics, ZWNJ, and Persian/Arabic digits.
- Explicitly does not collapse legally distinct terms such as فسخ and انفساخ.
- Integrated the scorer into existing `select_records` and `select_document_pages` functions; existing public strategy names are preserved for downstream compatibility.
- Adds audit metadata (`retrieval`, `minimum_score`) while preserving page labels, original text, source references, and complete structured records.
- Uses the existing safe fallback when no candidate reaches the conservative score threshold; it does not silently narrow context on weak matches.
- No embeddings, model downloads, external API calls, or new Python dependencies.

## Important scope boundary
This is a hybrid **lexical + fuzzy** local retriever, not a neural semantic-search model. It can recover spelling, morphology, and some OCR variations, but it cannot reliably infer deep conceptual equivalence when the wording is unrelated. This conservative choice avoids adding a large model/dependency or risking legal concept conflation. A future true semantic layer should be separately evaluated on a Persian legal benchmark and remain optional/offline.

## Verification
- Full test suite: **269 passed**.
- Focused retrieval/context optimizer tests: **10 passed**.
- `node --check miniapp/app.js`: passed.
- `python -m compileall -q legal_bot`: passed.
- `python preflight.py`: PASS.
- ZIP integrity: checked after packaging.
- No live Telegram test, external AI provider test, or concurrent-user load test was run.
