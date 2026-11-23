# MACHINA — Quarantine Cleanup & Dependency Isolation

Date: 2026-10-31

## What changed

- Removed 14 unverified/incomplete law or derivative-summary groups (770 records) from the active `legal_bot/data/iran/laws.json` corpus.
- Preserved those records outside the runtime search corpus at `legal_bot/data/iran/quarantine/inactive_laws.json` for audit and possible source-backed recovery. They are not loaded into the active search index.
- Added a fail-closed runtime blocklist in `legal_bot/laws.py` (`QUARANTINED_LAWS`) so accidental reintroduction into `laws.json` does not silently reactivate them.
- Updated `quarantine_manifest.json` with the new storage location, activation gate, and current counts.
- Marked the August 20 historical quality reports as superseded for current-state claims.
- Added regression tests for active-index exclusion, preservation outside the active corpus, and audit-count consistency.

## Groups moved out of active search

- قانون اساسی جمهوری اسلامی ایران — 177 records
- قانون تأمین اجتماعی — 118
- قانون مالیات بر ارزش افزوده — 53
- قانون تشکیلات و آیین دادرسی دیوان عدالت اداری — 124
- قانون حمایت از حقوق مصرف‌کنندگان — 22
- قانون بیمه — 36
- قانون حمایت از اطفال و نوجوانان — 51
- قانون الزام به ثبت رسمی معاملات اموال غیرمنقول — 15
- قانون حمایت از مالکیت صنعتی — 150
- قانون کیفیت اخذ پروانه وکالت دادگستری — 7
- Four dependent quick-reference/implementation bundles — 17 records total

Total: 14 groups / 770 records.

## Important correction to the earlier audit

The old `corpus_quality_report.json` (generated 2026-08-20) listed ten Civil/Commerce articles as missing text. All ten article IDs were checked in the restored `laws.json` used for this cleanup and currently contain non-empty text. They were therefore **not deleted** based on that stale report. This is only a structural check, not legal validation of their wording or current validity.

The Constitution was moved out of active search because the historical structural audit marked all 177 records invalid. This is not a judgment that the Constitution itself is invalid; it means this local extracted dataset is not safe to serve as legal text without reconstruction and source comparison.

## Dependency handling

- The application continues to use `laws.json` for active law search.
- Quarantined records are stored in a separate file that the normal loader does not import.
- The blocklist is an additional safety gate.
- `official_sources.json` and `law_catalog.json` remain as source/catalog metadata; they are not deleted because they are useful for later verification and do not make quarantined text searchable.
- No database schema, Mini App, Telegram menus, AI prompts, or case files were changed.

## QA

- `python preflight.py`: PASS
- `python -m compileall -q legal_bot`: PASS
- `node --check miniapp/app.js`: PASS
- `python -m pytest -q`: 437 passed
- Active law records: 8,409 across 159 groups
- Active search index: 8,496 records (8,409 law records + 87 samples/circulars)
- Quarantined groups: 14; quarantined records: 770

## Safety policy

No quarantined text is reactivated based only on its presence in a local file or a known URL. Reactivation requires primary-source confirmation, current-version and amendment reconciliation, article-by-article comparison, and a recorded checksum. For final legal authority, the project's Parliament-source requirement must be respected.
