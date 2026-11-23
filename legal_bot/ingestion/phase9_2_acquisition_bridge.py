# -*- coding: utf-8 -*-
"""Phase 9.2: bridge source routing to the existing secure PDF downloader.

This is a single-file, opt-in bridge. It never fetches HTML, follows print UI,
performs OCR, or writes to active legal banks. All accepted files remain in a
separate quarantine directory pending human review.
"""
from __future__ import annotations

import json
import tempfile
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .phase9_1_acquisition_policy import build_acquisition_plan, validate_acquisition_plan
from .secure_pdf_fetcher import PDFDownloadError, SecurePDFDownloader


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


def acquire_one_pdf_to_quarantine(
    *, source_id: str, source_url: str, staging_root: str | Path,
    direct_pdf_observed: bool, downloader: SecurePDFDownloader | None = None,
) -> dict[str, Any]:
    """Download one independently observed PDF into isolated quarantine.

    Network access occurs only when explicitly enabled in the supplied
    downloader policy. Ekhtebar remains secondary and is never promoted.
    """
    plan = build_acquisition_plan(source_id, source_url, direct_pdf_observed=direct_pdf_observed)
    if not validate_acquisition_plan(plan):
        raise ValueError("برنامه دریافت معتبر نیست")
    route = plan["route"]
    quarantine = Path(staging_root).resolve() / "phase9_2_quarantine"
    quarantine.mkdir(parents=True, exist_ok=True)
    result: dict[str, Any] = {
        "phase": "9.2", "source_id": source_id, "source_role": route["source_role"],
        "source_url": source_url, "route": route["route"],
        "status": "blocked", "reason": None, "download": None,
        "human_review_required": True, "active_bank_modified": False,
        "ocr_performed": False, "legal_validity_assessed": False,
    }
    parsed = urlparse(source_url)
    if not direct_pdf_observed or not parsed.path.lower().endswith(".pdf"):
        result["reason"] = "direct_pdf_asset_not_independently_observed"
    elif downloader is None:
        result["reason"] = "secure_downloader_not_configured"
    elif Path(downloader.storage_dir).resolve() != quarantine:
        result["reason"] = "downloader_storage_must_be_isolated_quarantine"
    else:
        try:
            downloaded = downloader.download(source_url)
            result["download"] = downloaded.to_dict()
            result["status"] = "downloaded_pending_human_review"
            if source_id == "ekhtebar":
                result["status"] = "secondary_downloaded_quarantine_only"
        except PDFDownloadError as exc:
            result["reason"] = str(exc)
    manifest = quarantine / "phase9_2_manifest.json"
    _atomic_json(manifest, result)
    result["manifest_path"] = str(manifest)
    return result
