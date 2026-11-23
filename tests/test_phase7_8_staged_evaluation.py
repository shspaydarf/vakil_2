import hashlib
import json

import pytest

from legal_bot.ingestion.human_review_gate import build_review_packet, record_review_decision
from legal_bot.ingestion.phase7_8_staged_evaluation import (
    Phase78EvaluationError, evaluate_approved_staging_package,
)


def _package(tmp_path):
    candidate_id = "candidate-78-test"
    package = tmp_path / candidate_id
    package.mkdir()
    text = "ماده ۱ ـ هر شخص مکلف به رعایت مقررات نمونه است."
    candidate = {
        "candidate_id": candidate_id,
        "catalog_document_id": "catalog-doc-78",
        "document_kind": "law",
        "title": "قانون نمونه مسئولیت مدنی آزمایشی",
        "source_document_sha256": "a" * 64,
        "original_pdf_path": "isolated/original.pdf",
        "records": [{"record_id": "record-78-1", "locator": {"article": "۱"},
                     "text_original": text, "source_page_refs": [1]}],
    }
    (package / "candidate.json").write_text(json.dumps(candidate, ensure_ascii=False), encoding="utf-8")
    manifest = {"candidate_id": candidate_id, "destination": "staging",
                "package_status": "staged_pending_human_review", "active_bank_modified": False,
                "import_performed": False}
    (package / "package_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    packet = build_review_packet({
        "document_id": "catalog-doc-78", "source_authority_at_discovery": "official_primary",
        "source_evidence": {"reference": "manual-evidence-78"},
        "record": {"title": candidate["title"]},
        "pdf_metadata": {"sha256": "a" * 64, "valid_pdf_signature": True,
                         "structural_validation_passed": True, "original_preserved": True},
        "extraction_metrics": {"page_count": 1, "low_text_pages": 0},
        "structure": {"articles": [{"number": "۱"}]},
    })
    ledger = record_review_decision(
        packet, None, decision="approved_for_staging", reviewer_id="reviewer-78",
        rationale="PDF original and extracted text compared for this test fixture.",
        completed_checklist=packet["checklist_required"], evidence_refs=["review-log:78"],
        decided_at="2026-11-01T12:00:00+00:00",
    )
    return package, candidate, packet, ledger


def test_approved_candidate_evaluates_only_in_staging(tmp_path):
    package, candidate, packet, ledger = _package(tmp_path)
    report = evaluate_approved_staging_package(
        package, ["قانون نمونه مسئولیت مدنی آزمایشی"], review_packet=packet,
        review_ledger=ledger, expected_record_ids={"قانون نمونه مسئولیت مدنی آزمایشی": ["record-78-1"]},
    )
    assert report["schema_version"] == "7.8"
    assert report["evaluation_status"] == "completed_metrics_assessed"
    assert report["expected_record_recall_assessed"] is True
    assert report["active_bank_unchanged"] is True
    assert report["active_bank_modified"] is False
    assert report["import_performed"] is False
    assert report["safety"]["legal_authenticity_confirmed"] is False
    assert report["query_reports"][0]["all_hits_staging_labelled"] is True


def test_expected_labels_missing_are_not_guessed(tmp_path):
    package, _, packet, ledger = _package(tmp_path)
    report = evaluate_approved_staging_package(
        package, ["قانون نمونه مسئولیت مدنی آزمایشی"], review_packet=packet, review_ledger=ledger,
    )
    assert report["expected_record_recall_at_k"] is None
    assert report["expected_record_recall_assessed"] is False
    assert "expected_relevance_labels_not_supplied_metrics_not_assessed" in report["blocker_codes"]


def test_tampered_review_ledger_is_rejected(tmp_path):
    package, _, packet, ledger = _package(tmp_path)
    ledger["events"][0]["rationale"] = "tampered"
    with pytest.raises(Phase78EvaluationError, match="ledger_integrity"):
        evaluate_approved_staging_package(package, ["عبارت آزمایشی"], review_packet=packet, review_ledger=ledger)


def test_non_approved_latest_human_decision_is_rejected(tmp_path):
    package, _, packet, ledger = _package(tmp_path)
    ledger = record_review_decision(
        packet, ledger, decision="needs_correction", reviewer_id="reviewer-2",
        rationale="Please correct OCR page 1.", completed_checklist=[], evidence_refs=["note:1"],
        decided_at="2026-11-01T13:00:00+00:00",
    )
    with pytest.raises(Phase78EvaluationError, match="latest_human_decision"):
        evaluate_approved_staging_package(package, ["عبارت آزمایشی"], review_packet=packet, review_ledger=ledger)


def test_candidate_review_identity_mismatch_is_rejected(tmp_path):
    package, _, packet, ledger = _package(tmp_path)
    packet = dict(packet)
    packet["document_id"] = "another-document"
    with pytest.raises(Phase78EvaluationError, match="packet_integrity"):
        evaluate_approved_staging_package(package, ["عبارت آزمایشی"], review_packet=packet, review_ledger=ledger)


def test_package_cannot_claim_active_destination(tmp_path):
    package, _, packet, ledger = _package(tmp_path)
    manifest_path = package / "package_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["destination"] = "active"
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(Phase78EvaluationError, match="isolated_staging"):
        evaluate_approved_staging_package(package, ["عبارت آزمایشی"], review_packet=packet, review_ledger=ledger)


def test_report_is_written_atomically_as_json(tmp_path):
    package, _, packet, ledger = _package(tmp_path)
    output = tmp_path / "reports" / "phase7_8.json"
    report = evaluate_approved_staging_package(
        package, ["قانون نمونه مسئولیت مدنی آزمایشی"], review_packet=packet,
        review_ledger=ledger, expected_record_ids={"قانون نمونه مسئولیت مدنی آزمایشی": ["record-78-1"]},
        output_path=output,
    )
    assert output.is_file()
    assert json.loads(output.read_text(encoding="utf-8"))["candidate_id"] == "candidate-78-test"
    assert report["report_path"] == str(output)


def test_invalid_query_limit_is_rejected(tmp_path):
    package, _, packet, ledger = _package(tmp_path)
    with pytest.raises(Phase78EvaluationError, match="limit_must_be"):
        evaluate_approved_staging_package(package, ["عبارت"], review_packet=packet, review_ledger=ledger, limit=99)


def test_tampered_review_packet_is_rejected(tmp_path):
    package, _, packet, ledger = _package(tmp_path)
    packet = dict(packet)
    packet["title"] = "دست‌کاری‌شده"
    with pytest.raises(Phase78EvaluationError, match="packet_integrity"):
        evaluate_approved_staging_package(package, ["عبارت آزمایشی"], review_packet=packet, review_ledger=ledger)
