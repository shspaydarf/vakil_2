# -*- coding: utf-8 -*-
"""Fail-closed acquisition workflow for the Phase 6.2 official PDF test.

The selected Parliament page is not itself a PDF asset URL. This module never
promotes a page URL to an asset URL and never falls back to a mirror. A direct
PDF URL must be discovered from the official page and supplied explicitly.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .secure_pdf_fetcher import PDFDownloadError, SecurePDFDownloader

OFFICIAL_HOST = "rc.majlis.ir"
CANDIDATE_ID = "MACHINA-PHASE6-1-IR-LAW-001"


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def acquire_selected_official_pdf(
    candidate: dict[str, Any],
    *,
    output_dir: str | Path,
    asset_url: str | None = None,
    downloader: SecurePDFDownloader | None = None,
    source_page_check: str = "unavailable",
    source_page_detail: str = "Official page could not be fetched from the execution environment.",
) -> dict[str, Any]:
    """Attempt acquisition only from a direct PDF URL on the official host.

    ``asset_url`` is intentionally mandatory for a network attempt. The known
    candidate URL is an HTML page, not a verified PDF asset. Mirror URLs are
    rejected before any downloader call.
    """
    candidate_id = candidate.get("candidate_id")
    official = candidate.get("sources", {}).get("preferred_official_source", {})
    page_url = official.get("url")
    timestamp = datetime.now(timezone.utc).isoformat()
    result: dict[str, Any] = {
        "phase": "6.2",
        "candidate_id": candidate_id,
        "document_title": candidate.get("document", {}).get("title"),
        "source_institution": official.get("institution"),
        "official_page_url": page_url,
        "official_page_check": {
            "status": source_page_check,
            "detail": source_page_detail,
        },
        "acquisition_status": "blocked",
        "reason_code": None,
        "attempted_asset_url": asset_url,
        "original_pdf": None,
        "sha256": None,
        "downloaded_at": None,
        "mirror_fallback_used": False,
        "active_bank_modified": False,
        "recorded_at": timestamp,
    }

    if candidate_id != CANDIDATE_ID or not page_url:
        result["reason_code"] = "candidate_identity_or_official_page_invalid"
    elif not asset_url:
        result["reason_code"] = "official_pdf_asset_url_unresolved"
        result["official_page_check"]["detail"] += " No direct official PDF asset URL was established; the HTML page URL is not treated as a PDF."
    else:
        parsed = urlparse(asset_url)
        if parsed.scheme != "https" or parsed.hostname != OFFICIAL_HOST or not parsed.path.lower().endswith(".pdf"):
            result["reason_code"] = "asset_url_not_verified_official_pdf_endpoint"
        elif downloader is None:
            result["reason_code"] = "secure_downloader_not_configured"
        else:
            try:
                downloaded = downloader.download(asset_url)
                result.update({
                    "acquisition_status": "downloaded_pending_integrity_review",
                    "reason_code": None,
                    "original_pdf": downloaded.path,
                    "sha256": downloaded.sha256,
                    "downloaded_at": downloaded.downloaded_at,
                    "pdf_size_bytes": downloaded.size_bytes,
                    "pdf_page_count": downloaded.page_count,
                    "final_source_url": downloaded.source_url,
                    "content_type": downloaded.content_type,
                })
            except PDFDownloadError as exc:
                result["reason_code"] = "secure_downloader_rejected_source"
                result["error"] = str(exc)

    target = Path(output_dir) / "phase6_2_acquisition_manifest.json"
    _atomic_json(target, result)
    result["manifest_path"] = str(target)
    return result
