# MACHINA Legal Engine — Phase 6.1 Report

## Decision
Selected one real-world candidate for the first controlled operational test:

**قانون احکام دائمی برنامه های توسعه کشور**

Candidate ID: `MACHINA-PHASE6-1-IR-LAW-001`

## Evidence reviewed
- A 31-page PDF mirror indexed by FAOLEX displays the header «مرکز پژوهش‌ها - طرح‌ها و لوایح».
- Its forwarding text states that the law was approved in the public session of 1395/11/10 and confirmed by the Guardian Council; the forwarding letter is numbered 33/96683 and dated 1395/12/01.
- The PDF also contains a letter numbered 1054 dated 1396/01/16, and repeatedly prints the Parliament Research Center page URL: `https://rc.majlis.ir/fa/law/print_version/1014070`.
- The official page URL could not be retrieved during this phase (HTTP 502). Therefore, official live access and official-PDF acquisition are **not confirmed**.

## Why this candidate
- It is not an exact top-level title in the current `laws.json` and is not an exact match in `law_catalog.json` or `official_sources.json`.
- At 31 pages, it is a manageable multi-page test document.
- Its visible structure contains nested clauses, notes, insertions into other laws, and numbering/layout irregularities. These provide a meaningful parser and OCR test while requiring careful human review.

## Source policy
The FAOLEX PDF is a discovery mirror only. It is **not** accepted as the official acquisition source. Phase 6.2 must retrieve the document from the allowlisted Parliament Research Center endpoint. If that endpoint remains unavailable, acquisition must stop; do not silently substitute the mirror.

## Scope and safety
- This phase only selected and documented the candidate.
- No PDF was downloaded into the project.
- No SHA-256 for a project-acquired original PDF exists yet.
- No OCR, extraction, legal parsing, staging, validation, import, or active-bank write was performed.
- The exact-title collision screen is not a complete semantic or article-level duplicate check; Phase 5.3 identity checks remain required after acquisition.
- Current amendments, repeal status, and enforceability have not been established.

## Phase 6.1 outcome
`selected_for_next_phase = true`

`approved_for_ingestion = false`

`approved_for_active_bank = false`

Next: Phase 6.2 — official-source PDF acquisition and original-file fingerprinting, subject to the secure downloader policy and allowlist.
