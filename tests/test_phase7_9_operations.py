import json

import pytest

from legal_bot.ingestion.phase7_9_operations import (
    Phase79Error, assess_activation_readiness, build_operations_dashboard,
    create_recovery_checkpoint, create_rollout_plan, validate_recovery_checkpoint,
    validate_rollout_plan, write_json_atomic,
)
from legal_bot.ingestion.bulk_processing_architecture import BatchPolicy


def candidates():
    return [
        {"document_id": "law-001", "source_id": "majlis", "source_class": "official_primary",
         "document_type": "law", "estimated_bytes": 1000, "estimated_pages": 10},
        {"document_id": "law-002", "source_id": "majlis", "source_class": "official_primary",
         "document_type": "law", "estimated_bytes": 1200, "estimated_pages": 12},
        {"document_id": "blog-001", "source_id": "blog", "source_class": "secondary",
         "document_type": "law"},
    ]


def test_rollout_plan_is_deterministic_and_plan_only():
    first = create_rollout_plan(candidates(), rollout_id="pilot-x")
    second = create_rollout_plan(candidates(), rollout_id="pilot-x")
    assert first["plan_sha256"] == second["plan_sha256"]
    assert len(first["items"]) == 2
    assert first["safety"]["network_access"] is False
    assert first["safety"]["active_bank_write"] is False
    assert first["safety"]["production_activation"] is False


def test_secondary_sources_deferred_by_default():
    plan = create_rollout_plan(candidates())
    assert all(x["source_id"] != "blog" for x in plan["items"])
    assert any(x["reason"] == "source_class_not_permitted:secondary" for x in plan["rejected"])


def test_rollout_policy_caps_documents_and_bytes():
    plan = create_rollout_plan(candidates(), policy=BatchPolicy(max_documents=1, max_total_bytes=1500))
    assert len(plan["items"]) == 1
    assert len(plan["deferred"]) == 1


def test_plan_tampering_fails_closed():
    plan = create_rollout_plan(candidates())
    plan["items"][0]["state"] = "completed"
    with pytest.raises(Phase79Error, match="integrity"):
        validate_rollout_plan(plan)


def test_dashboard_reports_progress_and_errors():
    plan = create_rollout_plan(candidates())
    dashboard = build_operations_dashboard(plan, observed_events=[
        {"document_id": plan["items"][0]["document_id"], "state": "blocked", "attempts": 2,
         "error_code": "PDF_INVALID"}, {"error_code": "HTTP_429"}])
    assert dashboard["state_counts"]["blocked"] == 1
    assert dashboard["error_counts"] == {"HTTP_429": 1, "PDF_INVALID": 1}
    assert dashboard["operational_status"] == "attention_required"
    assert dashboard["active_bank_modified"] is False


def test_recovery_checkpoint_is_bound_to_plan():
    plan = create_rollout_plan(candidates())
    checkpoint = create_recovery_checkpoint(plan, event_sequence=12, last_stable_event_id="evt-12")
    assert validate_recovery_checkpoint(plan, checkpoint)
    assert checkpoint["requires_event_log_replay"] is True
    assert checkpoint["safety"]["automatic_retry"] is False


def test_recovery_checkpoint_rejects_other_plan_or_tampering():
    plan = create_rollout_plan(candidates(), rollout_id="one")
    other = create_rollout_plan(candidates(), rollout_id="two")
    checkpoint = create_recovery_checkpoint(plan)
    assert not validate_recovery_checkpoint(other, checkpoint)
    checkpoint["event_sequence"] = 99
    assert not validate_recovery_checkpoint(plan, checkpoint)


def test_readiness_fails_closed_on_missing_and_false_evidence():
    result = assess_activation_readiness({"source_registry_reviewed": True,
                                         "real_pdf_sample_validated": False})
    assert result["readiness_status"] == "not_ready"
    assert "official_source_evidence_verified" in result["missing_checks"]
    assert "real_pdf_sample_validated" in result["failed_checks"]
    assert result["production_activation_performed"] is False


def test_readiness_only_reports_prerequisites_not_activation():
    keys = assess_activation_readiness({})["required_checks"]
    result = assess_activation_readiness({key: True for key in keys})
    assert result["readiness_status"] == "prerequisites_recorded"
    assert result["production_activation_performed"] is False
    assert result["human_release_authority_still_required"] is True


def test_atomic_artifact_write(tmp_path):
    path = write_json_atomic({"schema_version": "7.9", "ok": True}, tmp_path / "nested" / "plan.json")
    assert json.loads(path.read_text(encoding="utf-8")) == {"schema_version": "7.9", "ok": True}
    assert not list(path.parent.glob("*.tmp"))
