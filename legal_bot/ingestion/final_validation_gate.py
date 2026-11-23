# -*- coding: utf-8 -*-
"""Phase 4.6: consolidate validation evidence into a conservative import gate.

This is a workflow gate, not a legal-authenticity certificate. Missing evidence
fails closed. Even clean automated screening requires a recorded human decision
before a document can be marked eligible for Phase 5. Nothing is imported here.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

VALIDATOR_VERSION = "4.6.0"
REQUIRED_REPORTS = ("provenance", "metadata", "completeness", "version_conflict", "source_match")


def _dict(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if hasattr(value, "to_dict"):
        value = value.to_dict()
    elif hasattr(value, "__dataclass_fields__"):
        value = asdict(value)
    return dict(value) if isinstance(value, Mapping) else None


def _findings(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows = report.get("findings", [])
    result = []
    for row in rows if isinstance(rows, list) else []:
        if hasattr(row, "__dataclass_fields__"):
            row = asdict(row)
        if isinstance(row, Mapping):
            result.append(dict(row))
    return result


@dataclass(frozen=True)
class FinalValidationReport:
    checked_at: str
    validator_version: str
    document_id: str
    status: str
    phase5_eligible: bool
    checks: dict[str, str]
    blocking_reasons: list[dict[str, Any]]
    review_items: list[dict[str, Any]]
    human_decision: dict[str, Any]
    official_confirmation: bool = False
    legal_validity_proven: bool = False
    active_bank_changed: bool = False
    import_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def finalize_document_validation(
    document: Mapping[str, Any], reports: Mapping[str, Any], *,
    human_decision: Mapping[str, Any] | None = None,
) -> FinalValidationReport:
    """Build a fail-closed final report from Phase 4.1–4.5 evidence.

    `human_decision` must contain approved=True, a non-empty reviewer_id, and
    an ISO-8601 decided_at value to unlock Phase 5. A human decision cannot
    override critical provenance/hash failures or a missing official-source
    match. Version candidates and medium findings remain visible for review.
    """
    if not isinstance(document, Mapping) or not isinstance(reports, Mapping):
        raise ValueError("سند و گزارش‌های اعتبارسنجی باید ساختار معتبر داشته باشند")

    normalized = {key: _dict(reports.get(key)) for key in REQUIRED_REPORTS}
    checks: dict[str, str] = {}
    blockers: list[dict[str, Any]] = []
    review_items: list[dict[str, Any]] = []

    for key, report in normalized.items():
        if report is None:
            checks[key] = "missing"
            blockers.append({"code": "REQUIRED_REPORT_MISSING", "report": key,
                             "severity": "critical", "message": "گزارش الزامی این مرحله ارائه نشده است."})
        else:
            checks[key] = "received"
            for finding in _findings(report):
                severity = str(finding.get("severity", "info")).lower()
                item = {"report": key, **finding}
                if severity in {"critical", "high"}:
                    blockers.append(item)
                elif severity == "medium":
                    review_items.append(item)

    # Provenance: hashes and configured source chain must be internally consistent.
    provenance = normalized["provenance"]
    if provenance:
        origin = provenance.get("origin_consistency")
        eligible = provenance.get("eligible_for_next_review") is True
        if origin != "consistent_with_catalog" or not eligible:
            blockers.append({"code": "PROVENANCE_NOT_CLEARED", "report": "provenance",
                             "severity": "critical", "message": "زنجیره منشأ و دریافت برای عبور از دروازه کافی نیست."})
        else:
            checks["provenance"] = "consistent_with_catalog"
        if provenance.get("document_authenticity") != "not_proven":
            # Do not accept a component that claims stronger proof than its contract.
            blockers.append({"code": "UNEXPECTED_AUTHENTICITY_CLAIM", "report": "provenance",
                             "severity": "critical", "message": "وضعیت اصالت گزارش منشأ با قرارداد محافظه‌کارانه سازگار نیست."})

    metadata = normalized["metadata"]
    if metadata:
        status = metadata.get("overall_status")
        checks["metadata"] = str(status or "unknown")
        if status == "conflict_detected":
            blockers.append({"code": "METADATA_CONFLICT", "report": "metadata", "severity": "high",
                             "message": "تعارض مهم در شناسنامه سند وجود دارد."})
        elif status != "screening_passed":
            review_items.append({"code": "METADATA_REVIEW_REQUIRED", "report": "metadata", "severity": "medium",
                                 "message": "شناسنامه سند نیازمند بررسی انسانی یا تکمیل اطلاعات است."})

    completeness = normalized["completeness"]
    if completeness:
        status = completeness.get("status")
        checks["completeness"] = str(status or "unknown")
        if status == "critical_anomalies_found":
            blockers.append({"code": "COMPLETENESS_CRITICAL_ANOMALY", "report": "completeness", "severity": "high",
                             "message": "ناهنجاری مهم در صفحات یا ساختار سند وجود دارد."})
        elif status != "screening_no_anomaly_detected":
            review_items.append({"code": "COMPLETENESS_REVIEW_REQUIRED", "report": "completeness", "severity": "medium",
                                 "message": "کامل‌بودن ساختار سند نیازمند بازبینی است."})

    versions = normalized["version_conflict"]
    if versions:
        comparisons = versions.get("comparisons", [])
        checks["version_conflict"] = str(versions.get("status") or "unknown")
        if comparisons or _findings(versions):
            review_items.append({"code": "VERSION_RELATIONSHIP_REVIEW", "report": "version_conflict", "severity": "medium",
                                 "message": "رابطه نسخه‌ها یا اسناد مشابه باید پیش از ورود بررسی شود."})

    source_match = normalized["source_match"]
    if source_match:
        checks["source_match"] = str(source_match.get("status") or "unknown")
        if source_match.get("status") != "official_source_match_candidate":
            blockers.append({"code": "OFFICIAL_SOURCE_MATCH_MISSING", "report": "source_match", "severity": "high",
                             "message": "تطبیق نامزد با منبع رسمی در گزارش‌های ارائه‌شده وجود ندارد."})
        # Phase 4.5 intentionally never confirms a source officially.
        if source_match.get("official_confirmation") is not False:
            blockers.append({"code": "SOURCE_CONFIRMATION_FLAG_UNSAFE", "report": "source_match", "severity": "critical",
                             "message": "پرچم تأیید رسمی باید در این مرحله false باقی بماند."})

    decision = dict(human_decision or {})
    approved = decision.get("approved") is True
    reviewer = str(decision.get("reviewer_id") or "").strip()
    decided_at = str(decision.get("decided_at") or "").strip()
    valid_timestamp = False
    if decided_at:
        try:
            datetime.fromisoformat(decided_at.replace("Z", "+00:00"))
            valid_timestamp = True
        except ValueError:
            pass
    human_ok = approved and bool(reviewer) and valid_timestamp
    if decision and not human_ok:
        review_items.append({"code": "HUMAN_DECISION_INCOMPLETE", "report": "human_decision", "severity": "medium",
                             "message": "تصمیم انسانی باید شامل تأیید، شناسه بازبین و زمان معتبر باشد."})

    if blockers:
        status = "blocked_pending_correction"
        phase5_eligible = False
    elif review_items or not human_ok:
        status = "awaiting_human_review"
        phase5_eligible = False
    else:
        status = "approved_for_phase5_review"
        phase5_eligible = True

    # A Phase 5 eligibility flag is only a controlled hand-off, never an import.
    return FinalValidationReport(
        checked_at=datetime.now(timezone.utc).isoformat(), validator_version=VALIDATOR_VERSION,
        document_id=str(document.get("document_id") or document.get("id") or "unknown_document"),
        status=status, phase5_eligible=phase5_eligible, checks=checks,
        blocking_reasons=blockers, review_items=review_items,
        human_decision={"provided": bool(decision), "approved": approved,
                        "reviewer_id": reviewer or None, "decided_at": decided_at or None,
                        "decision_complete": human_ok},
    )


def write_final_validation_report(report: FinalValidationReport | Mapping[str, Any], output_path: str | Path) -> Path:
    """Atomically write the final validation decision as a JSON sidecar."""
    payload_obj = report.to_dict() if hasattr(report, "to_dict") else dict(report)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload_obj, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, target)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
    return target
