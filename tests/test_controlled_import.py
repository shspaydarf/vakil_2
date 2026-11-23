import hashlib
import json
from pathlib import Path

import pytest

from legal_bot.ingestion.staging_packages import create_candidate_package
from legal_bot.ingestion.controlled_import import prepare_staged_import, commit_staged_import


def _candidate():
    text = "متن ماده جدید برای ورود آزمایشی"
    return {
        "candidate_id": "candidate-57-001", "document_kind": "statute",
        "title": "قانون آزمایشی جدید", "jurisdiction": "IR",
        "source_authority_id": "majles", "source_url": "https://example.gov.ir/law.pdf",
        "source_document_sha256": "a" * 64, "acquired_at": "2026-11-01T10:00:00+00:00",
        "original_pdf_path": "evidence/original.pdf", "extraction_pipeline_version": "3.7.0",
        "extracted_text_sha256": "b" * 64, "validation_report_refs": ["11_final_validation_report.json"],
        "review_decision": {"approved": False, "status": "pending"},
        "records": [{"record_id": "record-57-001", "record_kind": "article",
                     "parent_document_id": "candidate-57-001", "locator": "ماده ۱",
                     "text_original": text, "source_page_refs": [1],
                     "record_sha256": hashlib.sha256(text.encode()).hexdigest()}],
    }


def _gate():
    return {"phase5_eligible": True, "active_bank_changed": False, "import_performed": False}


def _approval():
    return {"approved": True, "reviewer_id": "legal-reviewer-01",
            "decided_at": "2026-11-01T12:00:00+00:00",
            "source_review_completed": True, "legal_review_completed": True,
            "mapping_review_completed": True}


def _setup(tmp_path):
    (tmp_path / "laws.json").write_text(json.dumps({"قانون قدیمی": [{"ماده": "۱", "متن": "متن قدیمی"}]}, ensure_ascii=False), encoding="utf-8")
    package = create_candidate_package(_candidate(), data_dir=tmp_path, final_validation_report=_gate())
    replacement = {"قانون قدیمی": [{"ماده": "۱", "متن": "متن قدیمی"}],
                   "قانون آزمایشی جدید": [{"ماده": "۱", "متن": _candidate()["records"][0]["text_original"]}]}
    return Path(package["path"]), replacement


def test_prepare_requires_complete_human_review_and_does_not_write_bank(tmp_path):
    package, replacement = _setup(tmp_path)
    before = (tmp_path / "laws.json").read_bytes()
    with pytest.raises(PermissionError, match="complete_human_review"):
        prepare_staged_import(package, {"laws.json": replacement}, transaction_id="tx-57-a",
                              human_approval={"approved": True}, data_dir=tmp_path)
    result = prepare_staged_import(package, {"laws.json": replacement}, transaction_id="tx-57-b",
                                   human_approval=_approval(), data_dir=tmp_path)
    assert result["active_bank_modified"] is False
    assert result["import_performed"] is False
    assert (tmp_path / "laws.json").read_bytes() == before
    assert (Path(result["transaction"]["transaction_path"]) / "phase5_7_import_gate.json").is_file()


def test_prepare_rejects_removed_or_modified_existing_records(tmp_path):
    package, replacement = _setup(tmp_path)
    replacement["قانون قدیمی"] = []
    with pytest.raises(ValueError, match="append_only_violation"):
        prepare_staged_import(package, {"laws.json": replacement}, transaction_id="tx-57-c",
                              human_approval=_approval(), data_dir=tmp_path)


def test_prepare_requires_candidate_text_in_target_payload(tmp_path):
    package, replacement = _setup(tmp_path)
    replacement["قانون آزمایشی جدید"][0]["متن"] = "متن دیگری"
    with pytest.raises(ValueError, match="candidate_record_text_missing"):
        prepare_staged_import(package, {"laws.json": replacement}, transaction_id="tx-57-d",
                              human_approval=_approval(), data_dir=tmp_path)


def test_prepare_requires_exact_document_kind_target_and_final_gate(tmp_path):
    package, replacement = _setup(tmp_path)
    with pytest.raises(ValueError, match="document_kind_compatible"):
        prepare_staged_import(package, {"consultations.json": {"consultations": []}},
                              transaction_id="tx-57-e", human_approval=_approval(), data_dir=tmp_path)
    (package / "final_validation_report.json").write_text(json.dumps({"phase5_eligible": False}), encoding="utf-8")
    with pytest.raises(PermissionError, match="final_validation_gate"):
        prepare_staged_import(package, {"laws.json": replacement}, transaction_id="tx-57-f",
                              human_approval=_approval(), data_dir=tmp_path)


def test_commit_requires_second_confirmation_and_matching_review(tmp_path):
    package, replacement = _setup(tmp_path)
    before = (tmp_path / "laws.json").read_bytes()
    prepare_staged_import(package, {"laws.json": replacement}, transaction_id="tx-57-g",
                          human_approval=_approval(), data_dir=tmp_path)
    dry = commit_staged_import("tx-57-g", human_approval=_approval(), explicit_commit=False, data_dir=tmp_path)
    assert dry["commit_performed"] is False
    changed_approval = dict(_approval(), reviewer_id="someone-else")
    with pytest.raises(PermissionError, match="must_match"):
        commit_staged_import("tx-57-g", human_approval=changed_approval, explicit_commit=True, data_dir=tmp_path)
    assert (tmp_path / "laws.json").read_bytes() == before
    committed = commit_staged_import("tx-57-g", human_approval=_approval(), explicit_commit=True, data_dir=tmp_path)
    assert committed["status"] == "committed"
    assert committed["phase5_7_candidate_id"] == "candidate-57-001"
    assert "قانون آزمایشی جدید" in json.loads((tmp_path / "laws.json").read_text(encoding="utf-8"))


def test_staging_package_path_traversal_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="inside_staging"):
        prepare_staged_import(tmp_path, {"laws.json": {}}, transaction_id="tx-57-h",
                              human_approval=_approval(), data_dir=tmp_path)
