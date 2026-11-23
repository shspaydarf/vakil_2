# Phase 9.2 — Acquisition Bridge

`acquire_one_pdf_to_quarantine(...)` connects Phase 9.1 routing to the existing `SecurePDFDownloader` for one explicitly observed direct PDF URL.

- Provide a known `source_id` (`majles_rc` or `ekhtebar`) and HTTPS URL on its allowlisted host.
- Set `direct_pdf_observed=True` only after independently confirming that the URL is a PDF asset.
- Supply a downloader whose `storage_dir` is exactly `<staging_root>/phase9_2_quarantine` and whose download policy is explicitly enabled.
- The downloader retains its existing network and PDF safety checks.
- Ekhtebar remains secondary and quarantine-only. No output is promoted into the active bank.
- The bridge does not discover links, fetch HTML, automate the Majles print UI, run OCR, or decide legal validity.

If the URL or downloader is not verified/configured, the operation is blocked and a manifest is still written to quarantine.
