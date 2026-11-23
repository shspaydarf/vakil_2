# -*- coding: utf-8 -*-
"""Phase 4.7: connect PDF staging, validation reports and the final gate.

This coordinator is deliberately fail-closed and sidecar-only. It does not
fetch live sources unless a caller explicitly uses the queued-download helper
with an enabled SecurePDFDownloader. It never writes to the active law bank.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .document_pipeline import process_pdf_document
from .provenance_validator import validate_document_provenance, write_provenance_report
from .document_metadata_validator import validate_document_metadata
from .completeness_validator import validate_document_completeness, write_completeness_report
from .version_conflict_validator import compare_legal_document_versions, write_version_conflict_report
from .official_source_matcher import match_document_against_sources, write_source_match_report
from .final_validation_gate import finalize_document_validation, write_final_validation_report
from .secure_pdf_fetcher import SecurePDFDownloader, write_download_manifest

ORCHESTRATOR_VERSION = "4.7.0"


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "to_dict"):
        result = value.to_dict()
        return dict(result) if isinstance(result, Mapping) else {}
    raise ValueError("ورودی باید یک نگاشت یا شیء دارای to_dict باشد")


def _read_json(value: Mapping[str, Any] | str | Path) -> dict[str, Any]:
    if isinstance(value, (str, Path)):
        payload = json.loads(Path(value).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("فایل JSON باید یک شیء باشد")
        return payload
    return dict(value)


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(dict(payload), stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _validation_document(staging: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    structure = staging.get("structure") if isinstance(staging.get("structure"), dict) else {}
    normalized = staging.get("normalized") if isinstance(staging.get("normalized"), dict) else {}
    metadata = {
        "title": candidate.get("title") or structure.get("title"),
        "document_type": candidate.get("document_type") or structure.get("document_type"),
        "issuer": candidate.get("issuer") or structure.get("issuer"),
        "document_number": candidate.get("document_number"),
        "document_date": candidate.get("document_date") or candidate.get("page_date"),
        "enactment_date": candidate.get("enactment_date") or structure.get("dates", {}).get("approval_or_issue_date"),
        "notification_date": candidate.get("notification_date"),
        "publication_date": candidate.get("publication_date"),
    }
    return {
        "document_id": candidate.get("candidate_key") or candidate.get("source_record_id") or staging.get("source", {}).get("sha256"),
        "metadata": {key: value for key, value in metadata.items() if value not in (None, "")},
        "normalized_text": staging.get("document_text") or normalized.get("document_text") or "",
        "structure": structure,
        "pages": staging.get("pages", []),
        "source": staging.get("source", {}),
    }


def run_document_validation(
    pdf_path: str | Path,
    output_dir: str | Path,
    *,
    candidate: Mapping[str, Any],
    download_manifest: Mapping[str, Any] | str | Path,
    source_records: Sequence[Mapping[str, Any]],
    existing_documents: Sequence[Mapping[str, Any]] = (),
    human_decision: Mapping[str, Any] | None = None,
    run_ocr: bool = True,
) -> dict[str, Any]:
    """Run Phase 3.7 then Phase 4.1–4.6 using normalized adapters.

    `source_records` must contain the source metadata and source text already
    collected by an approved connector. No implicit web request is made.
    """
    candidate_data = _mapping(candidate)
    download_data = _read_json(download_manifest)
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)

    pipeline_result = process_pdf_document(
        pdf_path, target, document_type=str(candidate_data.get("document_type") or "unknown"),
        run_ocr=run_ocr,
    )
    staging_path = target / "05_staging_document.json"
    staging = _read_json(staging_path)
    document = _validation_document(staging, candidate_data)

    provenance = validate_document_provenance(
        candidate_data, download_data,
        pipeline_manifest=pipeline_result.to_dict(), pdf_path=pdf_path,
    )
    provenance_path = target / "06_provenance_report.json"
    write_provenance_report(provenance, provenance_path)

    extracted_metadata = {
        "title": (staging.get("structure") or {}).get("title"),
        "document_type": (staging.get("structure") or {}).get("document_type"),
        "issuer": (staging.get("structure") or {}).get("issuer"),
    }
    dates = (staging.get("structure") or {}).get("dates") or {}
    extracted_metadata["enactment_date"] = dates.get("approval_or_issue_date")
    extracted_metadata["document_date"] = dates.get("date")
    metadata = validate_document_metadata(candidate_data, extracted_metadata, candidate_data)
    metadata_path = target / "07_metadata_report.json"
    _atomic_json(metadata_path, metadata.to_dict())

    completeness = validate_document_completeness(
        staging.get("pages", []), staging.get("structure", {}),
        expected_page_count=(staging.get("source") or {}).get("page_count"),
        source_sha256=(staging.get("source") or {}).get("sha256"),
    )
    completeness_path = target / "08_completeness_report.json"
    write_completeness_report(completeness, completeness_path)

    comparison_docs = [document]
    for row in existing_documents:
        comparison_docs.append(_mapping(row))
    versions = compare_legal_document_versions(comparison_docs)
    versions_path = target / "09_version_conflict_report.json"
    write_version_conflict_report(versions, versions_path)

    normalized_source_records = [_mapping(row) for row in source_records]
    source_match = match_document_against_sources(
        document, normalized_source_records,
    )
    source_match_path = target / "10_source_match_report.json"
    write_source_match_report(source_match, source_match_path)

    reports = {
        "provenance": provenance,
        "metadata": metadata,
        "completeness": completeness,
        "version_conflict": versions,
        "source_match": source_match,
    }
    final = finalize_document_validation(document, reports, human_decision=human_decision)
    final_path = target / "11_final_validation_report.json"
    write_final_validation_report(final, final_path)

    result = {
        "orchestrator_version": ORCHESTRATOR_VERSION,
        "document_id": document["document_id"],
        "pipeline": pipeline_result.to_dict(),
        "reports": {
            "provenance": str(provenance_path), "metadata": str(metadata_path),
            "completeness": str(completeness_path), "version_conflict": str(versions_path),
            "source_match": str(source_match_path), "final": str(final_path),
        },
        "final_status": final.status,
        "phase5_eligible": final.phase5_eligible,
        "official_confirmation": False,
        "legal_validity_proven": False,
        "active_bank_changed": False,
        "import_performed": False,
    }
    _atomic_json(target / "12_integration_manifest.json", result)
    return result


def process_queued_candidate(
    queue: Any,
    candidate_key: str,
    downloader: SecurePDFDownloader,
    output_dir: str | Path,
    *,
    source_records: Sequence[Mapping[str, Any]],
    existing_documents: Sequence[Mapping[str, Any]] = (),
    human_decision: Mapping[str, Any] | None = None,
    run_ocr: bool = True,
) -> dict[str, Any]:
    """Download one queued item under downloader policy, then validate it.

    The caller must explicitly configure an enabled downloader. Queue state is
    marked downloaded after secure acquisition; validation status is separate.
    """
    rows = [row for row in queue.list_items() if row.get("candidate_key") == candidate_key]
    if not rows:
        raise ValueError("شناسه نامزد در صف دریافت پیدا نشد")
    row = rows[0]
    candidate = dict(row.get("candidate") or {})
    if not candidate.get("asset_url"):
        raise ValueError("نامزد صف فاقد نشانی PDF است")
    try:
        downloaded = downloader.download(str(candidate["asset_url"]))
        manifest_path = Path(output_dir) / "download_manifest.json"
        write_download_manifest(downloaded, manifest_path)
        queue.mark_result(candidate_key, success=True)
    except Exception as exc:
        queue.mark_result(candidate_key, success=False, error=type(exc).__name__)
        raise
    return run_document_validation(
        downloaded.path, output_dir, candidate=candidate,
        download_manifest=manifest_path, source_records=source_records,
        existing_documents=existing_documents, human_decision=human_decision,
        run_ocr=run_ocr,
    )
