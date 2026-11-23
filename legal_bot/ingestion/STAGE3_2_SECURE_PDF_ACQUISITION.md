# MACHINA Legal Engine — Stage 3.2

## Scope
Adds a bounded PDF acquisition component for documents already discovered by a source connector. This stage does not extract text, run OCR, alter the source PDF, or write to the active legal JSON bank.

## Safety controls
- Downloads remain opt-in (`ConnectorPolicy.allow_downloads=False` by default).
- Exact-host allowlisting is enforced for the initial URL and every redirect.
- DNS results must be globally routable; private, loopback, link-local and other non-global destinations are rejected to reduce SSRF risk.
- HTTPS certificate verification remains enabled; redirects are handled manually and bounded.
- Only HTTP 200 responses with PDF-compatible content types are accepted.
- Both declared and streamed byte counts are bounded by `max_asset_bytes`.
- PDF magic bytes, EOF marker, encryption state, internal structure and page count are checked with PyMuPDF.
- Original bytes are stored unchanged under a SHA-256 filename using an atomic write. A separate JSON manifest can record provenance.
- No embedded scripts, attachments, links, or other active content are executed.

## Integration contract
Use `SecurePDFDownloader(storage_dir, allowed_hosts=..., policy=...)` and call `download(asset_url)`. The returned `DownloadedPDF` contains path, digest, byte count, page count, final URL and timestamp. The caller may then record the result in the staging workflow. The active law bank is intentionally out of scope.

## Operational notes
Set `allow_downloads=True` only in a controlled deployment after source permission, robots policy and rate limits have been checked. DNS checks are repeated for redirects. Configure `max_asset_bytes` and `max_pages` conservatively. This component is not a malware scanner; it validates the transport and PDF container sufficiently for staging, while later processing should remain sandboxed and resource-limited.
