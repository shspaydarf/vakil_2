# -*- coding: utf-8 -*-
"""Phase 6.3: fail-closed integrity and provenance validation for an acquired official PDF.

This module validates acquisition evidence and file integrity only. It does not
certify legal authenticity, current force, amendments, or legal interpretation.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .official_pdf_acquisition import CANDIDATE_ID, OFFICIAL_HOST


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_official_pdf_evidence(
    acquisition_manifest: dict[str, Any],
    *,
    expected_candidate_id: str = CANDIDATE_ID,
    expected_title: str = "قانون احکام دائمی برنامه های توسعه کشور",
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """Validate manifest, official host, local PDF signature, hash and page count.

    A blocked acquisition remains blocked. No mirror or web text is accepted as
    a substitute for the original PDF. Success means technical evidence passed,
    not that the law's legal status or content has been authenticated.
    """
    result: dict[str, Any] = {
        "phase": "6.3",
        "candidate_id": acquisition_manifest.get("candidate_id"),
        "document_title": acquisition_manifest.get("document_title"),
        "validation_status": "blocked_pending_official_pdf",
        "reason_codes": [],
        "checks": {},
        "technical_integrity_passed": False,
        "legal_authenticity_confirmed": False,
        "current_force_confirmed": False,
        "active_bank_modified": False,
        "validated_at": datetime.now(timezone.utc).isoformat(),
    }

    def fail(code: str) -> None:
        result["reason_codes"].append(code)

    if acquisition_manifest.get("candidate_id") != expected_candidate_id:
        fail("candidate_id_mismatch")
    if acquisition_manifest.get("document_title") != expected_title:
        fail("document_title_mismatch")
    result["checks"]["candidate_identity"] = not result["reason_codes"]

    if acquisition_manifest.get("acquisition_status") != "downloaded_pending_integrity_review":
        fail("official_pdf_not_acquired")
    if acquisition_manifest.get("mirror_fallback_used") is not False:
        fail("mirror_fallback_not_allowed")

    source_url = acquisition_manifest.get("final_source_url") or acquisition_manifest.get("attempted_asset_url")
    parsed = urlparse(source_url or "")
    official_source_ok = parsed.scheme == "https" and parsed.hostname == OFFICIAL_HOST and parsed.path.lower().endswith(".pdf")
    result["checks"]["official_pdf_source_endpoint"] = official_source_ok
    if not official_source_ok:
        fail("official_pdf_source_endpoint_unverified")

    raw_path = acquisition_manifest.get("original_pdf")
    pdf_path = Path(raw_path) if raw_path else None
    file_ok = bool(pdf_path and pdf_path.is_file())
    result["checks"]["original_file_present"] = file_ok
    if not file_ok:
        fail("original_pdf_missing")

    if file_ok and pdf_path is not None:
        try:
            with pdf_path.open("rb") as stream:
                signature_ok = stream.read(5) == b"%PDF-"
            actual_hash = _sha256(pdf_path)
            expected_hash = acquisition_manifest.get("sha256")
            hash_ok = bool(expected_hash and actual_hash.lower() == str(expected_hash).lower())
            result["checks"]["pdf_signature"] = signature_ok
            result["checks"]["sha256_matches_manifest"] = hash_ok
            result["actual_sha256"] = actual_hash
            if not signature_ok:
                fail("pdf_signature_invalid")
            if not hash_ok:
                fail("sha256_mismatch")
            try:
                import fitz
                with fitz.open(pdf_path) as document:
                    page_count = document.page_count
                    structurally_valid = page_count > 0
            except Exception:
                page_count = 0
                structurally_valid = False
            result["pdf_page_count"] = page_count
            result["checks"]["pdf_structure_valid"] = structurally_valid
            if not structurally_valid:
                fail("pdf_structure_invalid")
            manifest_pages = acquisition_manifest.get("pdf_page_count")
            if manifest_pages is not None and int(manifest_pages) != page_count:
                result["checks"]["page_count_matches_manifest"] = False
                fail("page_count_mismatch")
            else:
                result["checks"]["page_count_matches_manifest"] = True
        except OSError:
            fail("original_pdf_unreadable")

    if not result["reason_codes"]:
        result["validation_status"] = "technical_integrity_passed_pending_human_legal_review"
        result["technical_integrity_passed"] = True

    if output_path is not None:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix(target.suffix + ".tmp")
        temp.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(target)
        result["report_path"] = str(target)
    return result
