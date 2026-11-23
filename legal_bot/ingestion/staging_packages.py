"""Phase 5.2: isolated staging/quarantine package creation (never imports bank data)."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .bank_architecture import DATA_DIR
from .record_identity import build_identity_manifest, canonical_document_family, scan_existing_identities, validate_lineage

PACKAGE_SCHEMA_VERSION = "5.2"
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,99}$")
SHA_RE = re.compile(r"^[a-fA-F0-9]{64}$")
ALLOWED_DOCUMENT_KINDS = {
    # Current five-family pipeline contract.
    "law", "regulation", "supreme_court_ruling", "administrative_court_ruling", "advisory_opinion",
    # Legacy values retained for existing callers and bank compatibility.
    "statute", "ruling", "consultation", "sample", "circular",
}
REQUIRED_ENVELOPE = (
    "candidate_id", "document_kind", "title", "jurisdiction", "source_authority_id",
    "source_url", "source_document_sha256", "acquired_at", "original_pdf_path",
    "extraction_pipeline_version", "extracted_text_sha256", "records",
    "validation_report_refs", "review_decision",
)
REQUIRED_RECORD = (
    "record_id", "record_kind", "parent_document_id", "locator", "text_original",
    "source_page_refs", "record_sha256",
)


def _sha(value: Any) -> bool:
    return isinstance(value, str) and SHA_RE.fullmatch(value) is not None


def _iso(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def validate_candidate(candidate: Any) -> dict[str, Any]:
    """Strict structural/integrity screening. This is not legal validation."""
    errors: list[str] = []
    if not isinstance(candidate, Mapping):
        return {"valid": False, "errors": ["candidate_must_be_object"]}
    missing = [key for key in REQUIRED_ENVELOPE if key not in candidate]
    errors.extend(f"missing:{key}" for key in missing)
    if missing:
        return {"valid": False, "errors": errors}

    if not isinstance(candidate["candidate_id"], str) or not ID_RE.fullmatch(candidate["candidate_id"]):
        errors.append("invalid:candidate_id")
    if candidate["document_kind"] not in ALLOWED_DOCUMENT_KINDS:
        errors.append("invalid:document_kind")
    if "document_family" in candidate and canonical_document_family(candidate.get("document_family")) is None:
        errors.append("invalid:document_family")
    for key in ("title", "jurisdiction", "source_authority_id", "source_url", "original_pdf_path", "extraction_pipeline_version"):
        if not isinstance(candidate[key], str) or not candidate[key].strip():
            errors.append(f"invalid:{key}")
    if not _sha(candidate["source_document_sha256"]):
        errors.append("invalid:source_document_sha256")
    if not _sha(candidate["extracted_text_sha256"]):
        errors.append("invalid:extracted_text_sha256")
    if not _iso(candidate["acquired_at"]):
        errors.append("invalid:acquired_at")
    if not isinstance(candidate["source_url"], str) or not candidate["source_url"].startswith("https://"):
        errors.append("invalid:source_url_requires_https")
    if not isinstance(candidate["validation_report_refs"], list) or not all(isinstance(x, str) and x.strip() for x in candidate["validation_report_refs"]):
        errors.append("invalid:validation_report_refs")
    decision = candidate["review_decision"]
    if not isinstance(decision, Mapping) or decision.get("approved") is not False:
        errors.append("review_decision_must_remain_pending_or_unapproved")
    records = candidate["records"]
    if not isinstance(records, list) or not records:
        errors.append("invalid:records_must_be_nonempty_list")
    else:
        seen: set[str] = set()
        for index, row in enumerate(records):
            prefix = f"records[{index}]"
            if not isinstance(row, Mapping):
                errors.append(f"{prefix}:must_be_object")
                continue
            for key in REQUIRED_RECORD:
                if key not in row:
                    errors.append(f"{prefix}:missing:{key}")
            if any(key not in row for key in REQUIRED_RECORD):
                continue
            rid = row["record_id"]
            if not isinstance(rid, str) or not ID_RE.fullmatch(rid):
                errors.append(f"{prefix}:invalid:record_id")
            elif rid in seen:
                errors.append(f"{prefix}:duplicate:record_id")
            else:
                seen.add(rid)
            if row["record_kind"] not in ALLOWED_DOCUMENT_KINDS and row["record_kind"] not in {"article", "paragraph", "clause", "holding", "opinion", "template", "circular_item"}:
                errors.append(f"{prefix}:invalid:record_kind")
            if row["parent_document_id"] != candidate["candidate_id"]:
                errors.append(f"{prefix}:parent_document_id_mismatch")
            if not isinstance(row["locator"], (str, int, Mapping)):
                errors.append(f"{prefix}:invalid:locator")
            if not isinstance(row["text_original"], str) or not row["text_original"].strip():
                errors.append(f"{prefix}:invalid:text_original")
            pages = row["source_page_refs"]
            if not isinstance(pages, list) or not pages or any(not isinstance(p, int) or p < 1 for p in pages):
                errors.append(f"{prefix}:invalid:source_page_refs")
            if not _sha(row["record_sha256"]):
                errors.append(f"{prefix}:invalid:record_sha256")
            elif isinstance(row["text_original"], str) and hashlib.sha256(row["text_original"].encode("utf-8")).hexdigest() != row["record_sha256"].lower():
                errors.append(f"{prefix}:record_sha256_mismatch")
    return {"valid": not errors, "errors": errors, "record_count": len(records) if isinstance(records, list) else 0}


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(_json_bytes(payload))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def create_candidate_package(
    candidate: Mapping[str, Any], *, data_dir: Path | str | None = None,
    final_validation_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Write a new isolated package; invalid/blocked candidates go to quarantine.

    A candidate is staged only when its schema is valid AND the Phase 4.6 report
    explicitly says phase5_eligible=true. Human approval is still required later.
    Existing package IDs are never overwritten. Active bank files are never touched.
    """
    validation = validate_candidate(candidate)
    lineage = validate_lineage(candidate) if isinstance(candidate, Mapping) else {"valid": False, "errors": ["candidate_must_be_object"], "relations": []}
    if not isinstance(candidate, Mapping) or not isinstance(candidate.get("candidate_id"), str) or not ID_RE.fullmatch(candidate.get("candidate_id", "")):
        raise ValueError("candidate_id نامعتبر است؛ مسیر بسته ساخته نشد")
    gate_ok = isinstance(final_validation_report, Mapping) and final_validation_report.get("phase5_eligible") is True and final_validation_report.get("active_bank_changed") is False and final_validation_report.get("import_performed") is False
    destination_name = "staging" if validation["valid"] and lineage["valid"] and gate_ok else "quarantine"
    root = Path(data_dir) if data_dir is not None else DATA_DIR
    identity_manifest = build_identity_manifest(candidate)
    duplicate_report = scan_existing_identities(candidate, root)
    base = root / "ingestion" / destination_name
    base.mkdir(parents=True, exist_ok=True)
    package_dir = base / candidate["candidate_id"]
    if package_dir.exists():
        raise FileExistsError(f"بسته‌ای با این شناسه از قبل وجود دارد: {candidate['candidate_id']}")
    temp_dir = Path(tempfile.mkdtemp(prefix=f".{candidate['candidate_id']}.", dir=str(base)))
    try:
        _atomic_json(temp_dir / "candidate.json", dict(candidate))
        _atomic_json(temp_dir / "records.json", candidate.get("records", []))
        _atomic_json(temp_dir / "schema_validation.json", validation)
        _atomic_json(temp_dir / "identity_manifest.json", identity_manifest)
        _atomic_json(temp_dir / "duplicate_report.json", duplicate_report)
        _atomic_json(temp_dir / "lineage_report.json", lineage)
        if final_validation_report is not None:
            _atomic_json(temp_dir / "final_validation_report.json", dict(final_validation_report))
        manifest = {
            "schema_version": PACKAGE_SCHEMA_VERSION,
            "candidate_id": candidate["candidate_id"],
            "package_status": "staged_pending_human_review" if destination_name == "staging" else "quarantined",
            "destination": destination_name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "schema_valid": validation["valid"],
            "lineage_valid": lineage["valid"],
            "duplicate_matches_reported": len(duplicate_report["matches"]),
            "automatic_merge_performed": False,
            "phase4_6_gate_passed": gate_ok,
            "human_approval_granted": False,
            "active_bank_modified": False,
            "import_performed": False,
        }
        _atomic_json(temp_dir / "package_manifest.json", manifest)
        # Atomic directory promotion; no overwrite is permitted.
        if package_dir.exists():
            raise FileExistsError(str(package_dir))
        os.rename(temp_dir, package_dir)
    except Exception:
        if temp_dir.exists():
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
        raise
    return {**manifest, "path": str(package_dir), "validation_errors": validation["errors"], "lineage_errors": lineage["errors"], "duplicate_matches": duplicate_report["matches"], "record_count": validation["record_count"]}
