import hashlib
import json
from pathlib import Path

import pytest

from legal_bot import laws
from legal_bot.ingestion.phase6_5_evaluation import evaluate_staged_candidate
from legal_bot.ingestion.staging_packages import create_candidate_package


def _candidate(candidate_id="phase65-fixture-001"):
    text = "ماده ۱ ـ هرگاه متعهد از انجام تعهد قراردادی خودداری کند، مسئول جبران خسارت است."
    return {
        "candidate_id": candidate_id, "document_kind": "statute", "title": "قانون آزمایشی مسئولیت قراردادی",
        "jurisdiction": "IR", "source_authority_id": "fixture-only", "source_url": "https://example.gov.ir/test.pdf",
        "source_document_sha256": "a" * 64, "acquired_at": "2026-11-01T10:00:00+00:00",
        "original_pdf_path": "fixture/original.pdf", "extraction_pipeline_version": "3.7.0",
        "extracted_text_sha256": "b" * 64, "validation_report_refs": ["11_final_validation_report.json"],
        "review_decision": {"approved": False, "status": "pending"},
        "records": [{"record_id": "fixture-record-001", "record_kind": "article", "parent_document_id": candidate_id,
                     "locator": "ماده ۱", "text_original": text, "source_page_refs": [2],
                     "record_sha256": hashlib.sha256(text.encode()).hexdigest()}],
    }


def _gate():
    return {"phase5_eligible": True, "active_bank_changed": False, "import_performed": False}


def test_phase65_runs_isolated_preview_and_reports_expected_recall(tmp_path):
    package = create_candidate_package(_candidate(), data_dir=tmp_path, final_validation_report=_gate())
    q = "مسئول جبران خسارت تعهد قراردادی"
    report = evaluate_staged_candidate(package["path"], [q], expected_record_ids={q: ["fixture-record-001"]})
    assert report["evaluation_status"] == "evaluation_complete_real_document_gate_blocked"
    assert report["expected_record_recall"] == 1.0
    assert report["active_bank_unchanged"] is True
    assert report["active_search_results_unchanged"] is True
    assert report["import_performed"] is False
    assert "real_official_pdf_technical_validation_not_passed" in report["blocker_codes"]


def test_phase65_does_not_claim_real_readiness_without_human_review(tmp_path):
    package = create_candidate_package(_candidate("phase65-fixture-002"), data_dir=tmp_path, final_validation_report=_gate())
    report = evaluate_staged_candidate(package["path"], ["مسئولیت قراردادی"],
        official_pdf_validation={"technical_integrity_passed": True, "legal_authenticity_confirmed": False, "current_force_confirmed": False})
    assert report["human_review_and_mapping_passed"] is False
    assert "human_review_and_explicit_mapping_not_approved" in report["blocker_codes"]


def test_phase65_blocks_empty_queries(tmp_path):
    package = create_candidate_package(_candidate("phase65-fixture-003"), data_dir=tmp_path, final_validation_report=_gate())
    with pytest.raises(ValueError, match="at_least_one"):
        evaluate_staged_candidate(package["path"], [])


def test_phase65_writes_auditable_report_without_bank_mutation(tmp_path):
    package = create_candidate_package(_candidate("phase65-fixture-004"), data_dir=tmp_path, final_validation_report=_gate())
    output = tmp_path / "phase6_5_evaluation_report.json"
    report = evaluate_staged_candidate(package["path"], ["مسئولیت قراردادی"], output_path=output)
    stored = json.loads(output.read_text(encoding="utf-8"))
    assert stored["candidate_id"] == report["candidate_id"]
    assert stored["active_bank_modified"] is False
    assert stored["report_path"] == str(output)
