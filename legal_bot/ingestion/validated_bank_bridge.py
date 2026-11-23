# -*- coding: utf-8 -*-
"""Phase 10.2.4: fail-closed bridge from validation evidence to bank append.

This adapter does not claim legal authenticity. It requires all five Phase 4
screening reports, then delegates publication/status/source checks, mapping,
page-budget enforcement, and dry-run transaction preparation. It never writes
active JSON banks. Missing, conflicting, or stronger-than-supported evidence
blocks the candidate.
"""
from __future__ import annotations
from typing import Any, Iterable, Mapping

from .autonomous_maintenance import MaintenancePolicy, run_autonomous_import

_REQUIRED = ("provenance", "metadata", "completeness", "version_conflict", "source_match")


def validate_machine_attestation(attestation: Mapping[str, Any]) -> None:
    if not isinstance(attestation, Mapping):
        raise ValueError("validation_attestation_missing")
    missing = [key for key in _REQUIRED if not isinstance(attestation.get(key), Mapping)]
    if missing:
        raise ValueError("validation_reports_missing:" + ",".join(missing))
    p = attestation["provenance"]
    if p.get("origin_consistency") != "consistent_with_catalog" or p.get("eligible_for_next_review") is not True:
        raise ValueError("provenance_not_cleared")
    if p.get("document_authenticity") != "not_proven":
        raise ValueError("authenticity_claim_not_supported")
    if attestation["metadata"].get("overall_status") != "screening_passed":
        raise ValueError("metadata_screening_not_passed")
    if attestation["completeness"].get("status") != "screening_no_anomaly_detected":
        raise ValueError("completeness_screening_not_passed")
    versions = attestation["version_conflict"]
    if versions.get("status") not in {"no_conflict_detected", "screening_no_conflict"} or versions.get("comparisons"):
        raise ValueError("version_conflict_requires_review")
    source = attestation["source_match"]
    if source.get("status") != "official_source_match_candidate" or source.get("official_confirmation") is not False:
        raise ValueError("official_source_match_screening_missing")
    for key in _REQUIRED:
        findings = attestation[key].get("findings", [])
        if not isinstance(findings, list):
            raise ValueError("validation_findings_malformed:" + key)
        if any(isinstance(row, Mapping) and str(row.get("severity", "")).lower() in {"critical", "high", "medium"} for row in findings):
            raise ValueError("validation_findings_require_review:" + key)


def run_validated_bank_bridge(
    items: Iterable[Mapping[str, Any]], *, data_dir: str,
    source_registry: Any, policy: MaintenancePolicy | None = None,
) -> dict[str, Any]:
    """Accept {candidate, validation_attestation} items; reject incomplete items.

    Valid candidates are handed to the autonomous staging routine, which only
    prepares a guarded transaction. A separate explicitly approved commit is
    required before any active bank can change. This is not a legal opinion and
    never treats source matching as proof of authenticity or current legal force.
    """
    accepted, rejected = [], []
    for index, item in enumerate(items):
        try:
            if not isinstance(item, Mapping) or not isinstance(item.get("candidate"), Mapping):
                raise ValueError("candidate_missing")
            validate_machine_attestation(item.get("validation_attestation"))
            accepted.append(dict(item["candidate"]))
        except Exception as exc:
            rejected.append({"index": index, "reason": str(exc)})
    if not accepted:
        return {"accepted_for_import": 0, "rejected_by_validation_gate": rejected,
                "processed": 0, "added": 0, "active_bank_changed": False,
                "official_authenticity_proven": False, "legal_validity_proven": False}
    result = run_autonomous_import(accepted, data_dir=data_dir,
                                   source_registry=source_registry, policy=policy)
    result["accepted_for_import"] = len(accepted)
    result["rejected_by_validation_gate"] = rejected
    result["official_authenticity_proven"] = False
    result["legal_validity_proven"] = False
    result["validation_gate"] = "phase4_machine_screening_passed"
    return result
