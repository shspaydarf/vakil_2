# -*- coding: utf-8 -*-
"""Phase 4.1: validate source provenance and acquisition-chain consistency.

This module assesses whether the recorded acquisition trail is internally
consistent and tied to a configured source. It does NOT cryptographically
prove that a legal instrument is authentic or currently in force.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

VALIDATOR_VERSION = "4.1.0"


@dataclass(frozen=True)
class ProvenanceFinding:
    code: str
    severity: str
    message: str


@dataclass
class ProvenanceReport:
    validator_version: str
    candidate_key: str | None
    source_id: str | None
    source_name: str | None
    origin_consistency: str
    document_authenticity: str
    checks: dict[str, str] = field(default_factory=dict)
    findings: list[ProvenanceFinding] = field(default_factory=list)
    source_sha256: str | None = None
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    eligible_for_next_review: bool = False

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["findings"] = [asdict(item) for item in self.findings]
        return result


def _load_catalog(catalog: str | Path | Mapping[str, Any] | None) -> dict[str, Any]:
    if catalog is None:
        path = Path(__file__).with_name("SOURCE_CATALOG_V1.json")
        return json.loads(path.read_text(encoding="utf-8"))
    if isinstance(catalog, Mapping):
        return dict(catalog)
    return json.loads(Path(catalog).read_text(encoding="utf-8"))


def _host(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
            return None
        return (parsed.hostname or "").lower() or None
    except (TypeError, ValueError):
        return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _finding(report: ProvenanceReport, code: str, severity: str, message: str) -> None:
    report.findings.append(ProvenanceFinding(code, severity, message))


def validate_document_provenance(
    candidate: Mapping[str, Any],
    download_manifest: Mapping[str, Any] | str | Path,
    *,
    source_catalog: str | Path | Mapping[str, Any] | None = None,
    pipeline_manifest: Mapping[str, Any] | str | Path | None = None,
    pdf_path: str | Path | None = None,
) -> ProvenanceReport:
    """Check configured source identity, URL hosts, hashes and pipeline linkage.

    The result is a provenance screening report, not a legal authenticity
    certificate. Missing evidence fails closed for origin consistency.
    """
    if isinstance(download_manifest, (str, Path)):
        download = json.loads(Path(download_manifest).read_text(encoding="utf-8"))
    else:
        download = dict(download_manifest)
    if isinstance(pipeline_manifest, (str, Path)):
        pipeline = json.loads(Path(pipeline_manifest).read_text(encoding="utf-8"))
    else:
        pipeline = dict(pipeline_manifest) if pipeline_manifest is not None else None

    source_id = str(candidate.get("source_id") or "")
    report = ProvenanceReport(
        validator_version=VALIDATOR_VERSION,
        candidate_key=candidate.get("candidate_key") or candidate.get("stable_key"),
        source_id=source_id or None,
        source_name=candidate.get("source_name"),
        origin_consistency="not_verified",
        document_authenticity="not_proven",
    )
    findings_before = len(report.findings)
    try:
        catalog = _load_catalog(source_catalog)
        sources = {str(row.get("source_id")): row for row in catalog.get("sources", [])}
        source = sources.get(source_id)
        if not source:
            report.checks["source_catalog"] = "failed"
            _finding(report, "UNKNOWN_SOURCE", "high", "شناسه منبع در فهرست منابع MACHINA وجود ندارد.")
        else:
            report.checks["source_catalog"] = "passed"
            allowed_hosts = {str(host).lower() for host in source.get("allowed_hosts", [])}
            page_host = _host(str(candidate.get("page_url") or ""))
            asset_host = _host(str(candidate.get("asset_url") or ""))
            downloaded_host = _host(str(download.get("source_url") or ""))
            for label, host in (("candidate_page_host", page_host), ("candidate_asset_host", asset_host), ("download_source_host", downloaded_host)):
                if host is None:
                    if label == "candidate_asset_host" and not candidate.get("asset_url"):
                        report.checks[label] = "not_provided"
                    else:
                        report.checks[label] = "failed"
                        _finding(report, "INVALID_SOURCE_URL", "high", f"نشانی ثبت‌شده برای {label} معتبر نیست.")
                elif host not in allowed_hosts:
                    report.checks[label] = "failed"
                    _finding(report, "HOST_NOT_ALLOWLISTED", "high", f"دامنه {host} در فهرست مجاز منبع ثبت نشده است.")
                else:
                    report.checks[label] = "passed"
            if page_host and downloaded_host and page_host != downloaded_host:
                report.checks["page_download_host_match"] = "failed"
                _finding(report, "PAGE_DOWNLOAD_HOST_MISMATCH", "medium", "دامنه صفحه معرفی سند با دامنه دریافت فایل متفاوت است.")
            else:
                report.checks["page_download_host_match"] = "passed" if page_host and downloaded_host else "not_checked"

        expected_hash = str(download.get("sha256") or "").lower()
        if len(expected_hash) != 64 or any(ch not in "0123456789abcdef" for ch in expected_hash):
            report.checks["download_hash_format"] = "failed"
            _finding(report, "INVALID_DOWNLOAD_HASH", "high", "هش SHA-256 در مانیفست دریافت معتبر نیست.")
        else:
            report.checks["download_hash_format"] = "passed"
            report.source_sha256 = expected_hash

        if pdf_path is not None:
            file_path = Path(pdf_path)
            if not file_path.is_file():
                report.checks["pdf_file_hash"] = "failed"
                _finding(report, "PDF_FILE_MISSING", "high", "فایل PDF برای تطبیق هش پیدا نشد.")
            else:
                actual_hash = _sha256(file_path)
                if actual_hash != expected_hash:
                    report.checks["pdf_file_hash"] = "failed"
                    _finding(report, "PDF_HASH_MISMATCH", "critical", "هش فایل PDF با مانیفست دریافت مطابقت ندارد.")
                else:
                    report.checks["pdf_file_hash"] = "passed"
        else:
            report.checks["pdf_file_hash"] = "not_checked"

        if pipeline is not None:
            pipeline_hash = str(pipeline.get("source_sha256") or "").lower()
            if pipeline_hash and pipeline_hash == expected_hash:
                report.checks["pipeline_source_hash"] = "passed"
            else:
                report.checks["pipeline_source_hash"] = "failed"
                _finding(report, "PIPELINE_HASH_MISMATCH", "high", "هش سند در مانیفست پردازش با هش دریافت اولیه یکسان نیست.")
        else:
            report.checks["pipeline_source_hash"] = "not_checked"

        downloaded_url = str(download.get("source_url") or "")
        if not download.get("downloaded_at") or not downloaded_url:
            report.checks["acquisition_metadata"] = "failed"
            _finding(report, "INCOMPLETE_ACQUISITION_METADATA", "medium", "زمان دریافت یا نشانی نهایی دریافت در مانیفست موجود نیست.")
        else:
            report.checks["acquisition_metadata"] = "passed"

        # Metadata agreement is advisory only; source pages may omit fields.
        for field_name in ("title", "issuer", "document_number", "document_date"):
            candidate_value = str(candidate.get(field_name) or "").strip()
            manifest_value = str(download.get(field_name) or "").strip()
            if candidate_value and manifest_value and candidate_value != manifest_value:
                report.checks[f"metadata_{field_name}"] = "mismatch"
                _finding(report, "METADATA_MISMATCH", "medium", f"مقدار {field_name} در اطلاعات کشف و مانیفست یکسان نیست.")
            else:
                report.checks[f"metadata_{field_name}"] = "consistent_or_unavailable"

    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        report.checks["validator_execution"] = "failed"
        _finding(report, "VALIDATOR_INPUT_ERROR", "high", f"ورودی اعتبارسنجی قابل خواندن نیست: {type(exc).__name__}.")

    failed = any(value in {"failed", "mismatch"} for value in report.checks.values())
    report.origin_consistency = "inconsistent" if failed else "consistent_with_catalog" if report.checks.get("source_catalog") == "passed" else "not_verified"
    # A source-host match and hashes are not a digital signature. Never label as authentic.
    report.document_authenticity = "not_proven"
    report.eligible_for_next_review = (not failed and report.checks.get("source_catalog") == "passed"
                                        and report.checks.get("download_hash_format") == "passed")
    if not report.eligible_for_next_review:
        _finding(report, "HUMAN_REVIEW_REQUIRED", "high", "منشأ سند تأیید نشد؛ بررسی انسانی و تطبیق با منبع رسمی لازم است.")
    else:
        _finding(report, "AUTHENTICITY_NOT_CERTIFIED", "info", "زنجیره منشأ با فهرست منابع و هش‌ها سازگار است؛ اصالت حقوقی سند همچنان اثبات نشده است.")
    return report


def write_provenance_report(report: ProvenanceReport | Mapping[str, Any], path: str | Path) -> Path:
    """Atomically write a sidecar report; never changes the source document."""
    import os
    import tempfile
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = report.to_dict() if isinstance(report, ProvenanceReport) else dict(report)
    fd, temp_name = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, target)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return target
