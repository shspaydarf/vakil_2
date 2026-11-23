# MACHINA Legal Engine — Phase 1 Audit & Data Contract

**Date:** 2026-10-31  
**Base archive:** `MACHINA_Quarantine_Cleanup_With_Permanent_Warning_2026-10-31.zip`  
**Phase:** 1 of 8 — inspect the current legal corpus and define safe ingestion boundaries  
**Implementation status:** Audit/design only. No production code, existing legal JSON, search index, or Mini App behavior was changed in this phase.

## 1. Executive decision

MACHINA should keep its current local legal corpus as the primary offline/searchable library. The new collector is an additive subsystem: it discovers documents, downloads PDFs, extracts text, validates metadata and provenance, and then proposes or performs controlled additions to the existing JSON categories.

**Do not replace the current JSON bank, migrate it to a new database, normalize/rewrite its existing records, or let the collector overwrite existing text.** The first implementation should write only to a separate staging area and a machine-readable ingestion registry. Import into active JSON files comes only after the staging pipeline passes its acceptance tests.

## 2. Current corpus inventory

The following counts were measured directly from the supplied archive:

| Asset | Current count | Role |
|---|---:|---|
| `laws.json` | 159 law/document groups; 8,409 records | Main statute/regulation corpus |
| Runtime-accepted law records | 8,398 | Records accepted by current `laws.py` loader |
| Runtime-rejected law records | 11 | Excluded by existing structural/quality checks |
| `quarantine/inactive_laws.json` | 14 groups; 770 records | Intentionally inactive records; do not reactivate automatically |
| `rulings.json` | 159 Supreme Court General Assembly rulings + 127 Administrative Justice Court rulings | Judicial decisions |
| `consultations.json` | 179 | Legal Department advisory opinions |
| `samples_and_circulars.json` | 78 samples + 20 circulars | Templates and circular/reference material |
| `legal_glossary.json` | 400 entries | Legal terms |
| `important_terms.json` | 1,478 entries | Search vocabulary |
| `official_sources.json` | 5 authority entries; 33 law-source entries | Existing source registry |
| `active_user_pdf_sources.json` | 30 source entries | Provenance for user-supplied PDF imports |
| `law_catalog.json` | 42 `present_laws`; 23 `pending_foundation`; 52 `level1_missing_laws` | Coverage/catalog metadata (categories can overlap with other lists) |

There are 31 JSON files under `legal_bot/data/iran`; all parsed successfully during this audit. The current Python legal loader imported successfully in the audit environment and produced 8,398 accepted law records, 286 ruling records, 179 consultation records, 78 sample records, and 20 circular records.

**Counting note:** These are counts of records/groups, not counts of unique enacted legal provisions. A single group may contain amendments, repeated provisions, notes, or extracted records. Do not present the totals as the number of unique laws in Iran.

## 3. Existing data shape and compatibility findings

### 3.1 Main laws JSON

`laws.json` is a dictionary keyed by Persian document title. Each value is normally a list of article-like objects. The common fields are:

- `ماده` — article/section locator
- `متن` — extracted legal text
- `کلمات_کلیدی` — optional keywords
- `یادداشت_تنقیح` — optional editorial/consolidation note
- `منبع` / `به‌روزرسانی` — optional provenance/update fields

There are **8 distinct record shapes** in the current corpus. In particular, 467 newer records use additional fields such as `id`, `law_title`, `article_number`, `source_type`, `source_file`, and `content_status`, while older records use the compact Persian-key schema. This is not a reason to rewrite the bank. The collector must adapt its output to the established category format and keep detailed document-level provenance in a separate registry.

### 3.2 Judicial decisions and advisory opinions

`rulings.json` is an object with `metadata`, `rulings`, and `diwan_adalat_rulings`. The two ruling lists use similar but not perfectly uniform fields, including `نوع`, `مرجع`, `شماره`, `تاریخ`, `عنوان`, `متن`, source and text-status fields.

`consultations.json` is an object with `metadata` and `consultations`. Each record currently includes `شماره`, `تاریخ`, `سؤال`, `نظریه`, `مرجع`, `منبع_فایل`, and `وضعیت_متن`, with optional topic/notes fields. The audit found legacy spelling/field variants for the binding-status field; the new collector must not silently rename existing fields.

`samples_and_circulars.json` has separate `samples` and `circulars` lists. These are not statutory texts and must not be mixed into the law-article list.

### 3.3 Existing source and status metadata is distributed

Source/provenance information currently exists in several places:

- `official_sources.json`
- `active_user_pdf_sources.json`
- `law_catalog.json`
- `quarantine_manifest.json`
- the hard-coded `QUARANTINED_LAWS` gate in `legal_bot/laws.py`

This duplication creates a risk of inconsistent status if the new collector starts editing all these files. For the first collector version, do not try to unify or rewrite these legacy registries. Give the new ingestion subsystem its own sidecar registry and make it the single source of truth for documents discovered by the new engine. A later migration can be considered after the pipeline is stable.

## 4. Existing reusable technical components

The project already includes:

- **PyMuPDF** (`PyMuPDF` dependency) for PDF reading/rendering.
- **pytesseract** for OCR invocation.
- Existing Persian OCR preparation, text-quality diagnostics, and PDF extraction functions in `legal_bot/files.py`.
- Existing Persian legal text cleanup and OCR normalization utilities.
- Existing source lookup and citation-envelope helpers in `legal_bot/knowledge.py`.
- Existing runtime legal indexing in `legal_bot/laws.py`.

Therefore, we should reuse the current PDF/OCR stack rather than add another OCR framework immediately. The collector will need its own document-size/page limits and quality checks because user-upload extraction limits are not necessarily suitable for unattended source collection. Tesseract itself and the Persian trained data must be installed in the deployment environment; having `pytesseract` in `requirements.txt` alone does not prove the OCR engine is available.

**Runtime constraint:** the current legal indexes are built when `legal_bot/laws.py` is imported. Updating JSON files on disk does not necessarily refresh the running process's in-memory indexes. Phase 8 must either perform a safe controlled reload or schedule activation/restart after a successful import. The first version should not mutate active JSON while the bot is serving requests.

## 5. Source policy for the new collector

The collector must distinguish **discovery source** from **legal authority**:

1. **Majles / Parliament source:** preferred source for discovering and checking the text of laws passed by Parliament, in line with the project's stated policy. The exact page/document and publication metadata must be retained.
2. **Ekhtbar:** useful discovery and indexing source for locating new laws, regulations, rulings, and advisory opinions. It is not, by itself, proof that a text is authentic, complete, or currently in force.
3. **Court/Judicial issuing authority:** for Supreme Court and Administrative Justice Court decisions, the issuing court's own official publication/source is the final authority to verify the decision text and number.
4. **Legal Department / Judiciary:** for advisory opinions, the issuing legal department's official record is the final authority. Ekhtbar may locate the opinion but cannot replace issuer verification.

A source URL being reachable is not equivalent to verifying the text. A PDF downloaded from a discovery source must retain that discovery URL and separately record whether an official issuer copy was located and checked.

The current `official_sources.json` has five authorities and a priority ordering that does not fully reflect the user's latest policy preference. This phase records that discrepancy but intentionally does not rewrite the legacy registry. The new collector's source rules should follow the policy above.

## 6. Proposed ingestion contract (additive; no legacy schema rewrite)

The collector should maintain a new sidecar registry, provisionally:

`legal_bot/data/iran/ingestion_registry.json`

Each discovered document should have a stable document ID and fields equivalent to:

- `document_id`: stable internal identifier
- `document_type`: `law`, `regulation`, `supreme_court_ruling`, `administrative_court_ruling`, `advisory_opinion`, `circular`, or another explicitly supported type
- `title`, `issuing_authority`, `document_number`, `adoption_date`, `publication_date`, `effective_date` (nullable when unknown)
- `discovery_source_id`, `discovery_url`
- `official_source_id`, `official_url`, `official_match_status`
- `retrieved_at`, `file_sha256`, `original_filename`, `stored_pdf_path`
- `extraction_method` (`native_pdf_text` or `persian_ocr`), `page_count`, `extracted_text_path`, `extraction_quality`, `parser_version`
- `duplicate_of` (nullable), `target_json`, `target_group`, `target_record_ids`
- `workflow_status`: `discovered`, `downloaded`, `extracted`, `needs_review`, `validated`, `imported`, `rejected`, or `superseded`
- `validation_checks` and `review_notes`

This registry stores provenance and workflow state. Existing JSON record schemas remain unchanged. The legal text itself is stored in the appropriate existing category only after passing the relevant checks. Original PDFs and extracted text should be retained in a separate archive/staging directory so an imported JSON record can always be traced back to its source file.

### Safe import rules

- Never overwrite an existing law/article/ruling/opinion solely because a new PDF has the same title.
- Compare stable identifiers first (issuer, number, date, title, article locator); use file hash and normalized-text fingerprint as additional duplicate checks.
- Add genuinely new documents only to the matching JSON category.
- If a document is an amendment, store it as an amendment document or link it to the base law; do not silently replace the base text or claim that the base law is consolidated.
- If OCR is uncertain, pages are missing, metadata conflicts, the issuer cannot be confirmed, or current legal effect is unclear, keep it in `needs_review`.
- Keep previous versions and an append-only change log. No destructive replacement.
- Quarantined groups remain quarantined unless a separate explicit source-backed review authorizes activation. The permanent quarantine warning remains in force.

## 7. Recommended first release scope

To keep the project medium-complexity and achievable:

1. Start with **Ekhtbar discovery + one document type**, preferably advisory opinions or a small sample of rulings, because the source page/listing format can be tested without immediately touching the main laws corpus.
2. Download a small number of PDFs into staging only.
3. Reuse the existing PDF extraction/OCR functions where practical.
4. Produce structured metadata and extracted text; do not import into active JSON yet.
5. Verify the source and text manually for the pilot set.
6. Only after the pilot is repeatable, add Parliament law discovery and automatic safe import.

This is a deliberate safety boundary, not a reduction in the final ambition.

## 8. Phase 1 completion checklist

- [x] Inspected current project archive and legal data tree.
- [x] Counted current law, ruling, consultation, sample, circular, glossary, and term records.
- [x] Inspected actual record schemas and found schema variants.
- [x] Confirmed the existing PDF/OCR toolchain can be reused.
- [x] Identified existing source-registry duplication and runtime index-refresh constraint.
- [x] Defined discovery-source versus final-authority policy.
- [x] Defined additive ingestion metadata contract and safe import rules.
- [x] Confirmed this phase made no production code or existing legal-data changes.

## 9. Next phase

**Phase 2 — Source connectors and discovery.** First inspect the actual page/link structures and access behavior of the agreed sources. Build read-only discovery for Ekhtbar first, record candidate URLs and metadata, and do not download/import at scale until the source connector passes tests. Add the Parliament connector after the same discovery interface is stable.
