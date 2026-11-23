import json

import pytest

from legal_bot.ingestion.final_validation_gate import (
    finalize_document_validation, write_final_validation_report,
)

DOC = {"document_id": "law-42"}


def clean_reports():
    return {
        "provenance": {"origin_consistency": "consistent_with_catalog", "document_authenticity": "not_proven", "eligible_for_next_review": True, "findings": []},
        "metadata": {"overall_status": "screening_passed", "findings": []},
        "completeness": {"status": "screening_no_anomaly_detected", "findings": []},
        "version_conflict": {"status": "no_candidate_relationship_detected", "comparisons": [], "findings": []},
        "source_match": {"status": "official_source_match_candidate", "official_confirmation": False, "findings": []},
    }


def human_ok():
    return {"approved": True, "reviewer_id": "reviewer-17", "decided_at": "2026-11-01T10:00:00+03:30"}


def test_missing_report_fails_closed():
    reports = clean_reports()
    reports.pop("provenance")
    result = finalize_document_validation(DOC, reports, human_decision=human_ok())
    assert result.status == "blocked_pending_correction"
    assert result.phase5_eligible is False


def test_clean_automated_reports_still_need_human_decision():
    result = finalize_document_validation(DOC, clean_reports())
    assert result.status == "awaiting_human_review"
    assert result.phase5_eligible is False


def test_complete_human_approval_allows_phase5_handoff_not_import():
    result = finalize_document_validation(DOC, clean_reports(), human_decision=human_ok())
    assert result.status == "approved_for_phase5_review"
    assert result.phase5_eligible is True
    assert result.import_performed is False
    assert result.active_bank_changed is False
    assert result.legal_validity_proven is False


def test_critical_provenance_failure_cannot_be_overridden_by_human():
    reports = clean_reports()
    reports["provenance"]["origin_consistency"] = "inconsistent"
    result = finalize_document_validation(DOC, reports, human_decision=human_ok())
    assert result.status == "blocked_pending_correction"
    assert result.phase5_eligible is False


def test_metadata_conflict_blocks_gate():
    reports = clean_reports()
    reports["metadata"]["overall_status"] = "conflict_detected"
    result = finalize_document_validation(DOC, reports, human_decision=human_ok())
    assert result.status == "blocked_pending_correction"


def test_version_candidate_requires_review():
    reports = clean_reports()
    reports["version_conflict"]["comparisons"] = [{"relationship": "same_identity_different_text_candidate"}]
    result = finalize_document_validation(DOC, reports, human_decision=human_ok())
    assert result.status == "awaiting_human_review"
    assert result.phase5_eligible is False


def test_incomplete_human_identity_does_not_approve():
    decision = {"approved": True, "reviewer_id": "reviewer-17"}
    result = finalize_document_validation(DOC, clean_reports(), human_decision=decision)
    assert result.phase5_eligible is False


def test_report_is_written_atomically(tmp_path):
    result = finalize_document_validation(DOC, clean_reports())
    path = write_final_validation_report(result, tmp_path / "08_final_validation_report.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["validator_version"] == "4.6.0"
    assert payload["active_bank_changed"] is False


def test_invalid_inputs_rejected():
    with pytest.raises(ValueError):
        finalize_document_validation([], clean_reports())
