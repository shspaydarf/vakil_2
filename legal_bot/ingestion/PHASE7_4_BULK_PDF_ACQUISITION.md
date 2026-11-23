# Phase 7.4 — Secure Batch PDF Acquisition

## Scope
This phase adds a controlled batch runner on top of the Phase 7.2 Source Registry,
Phase 7.3 Document Catalog, and the existing `SecurePDFDownloader`.

## Safety contract
- Planning is offline and deterministic; dry-run is the default.
- Live acquisition requires `BatchAcquisitionPolicy(allow_downloads=True)` **and**
  a downloader whose connector policy also explicitly enables downloads.
- Only catalog entries with `discovery_status=discovered` from a `verified`
  `official_primary` source and an allowed canonical URL are eligible.
- Source policy is revalidated immediately before every download.
- Requests are sequential, paced by the source registry's minimum interval, and
  bounded by document, per-source, byte, and page budgets.
- There are no automatic retries. HTTP 403, 429, and challenge errors stop/defer
  the batch; no CAPTCHA or access-control bypass is attempted.
- Existing secure downloader checks remain in force: exact host allowlist, public
  DNS/IP validation, TLS verification, redirect limits, content type, byte cap,
  PDF signature/EOF, PyMuPDF structural validation, and SHA-256 storage.
- Acquisition state is atomically persisted and reruns skip already acquired
  document IDs. Original PDFs remain content-addressed by SHA-256.
- No OCR, legal-validity decision, source-authority upgrade, or active JSON bank
  write occurs in this phase.

## API
- `BatchAcquisitionPolicy`: conservative batch resource limits; downloads off by default.
- `BatchPDFAcquisition.plan(...)`: offline plan from catalog IDs.
- `BatchPDFAcquisition.execute(..., dry_run=True)`: dry-run by default; set
  `dry_run=False` only after explicit policy opt-ins and human operational approval.
- `acquisition_policy_summary()`: machine-readable safety summary.

## Important limitations
The batch runner is an orchestration layer; it does not discover document URLs.
It relies on the pre-existing secure downloader for the actual HTTP/PDF checks.
The test suite uses controlled fixtures/fake downloaders for batch orchestration.
No live request to Parliament or Ekhtebar was made and no real official PDF was
acquired or verified in this phase. A verified source record is an administrative
assertion backed by recorded evidence; it does not itself establish legal validity.
