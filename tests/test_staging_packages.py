import hashlib
import json
from pathlib import Path

import pytest

from legal_bot.ingestion.staging_packages import create_candidate_package, validate_candidate


def _candidate(candidate_id="candidate-001"):
    text = "متن آزمایشی ماده یک"
    return {
        "candidate_id": candidate_id,
        "document_kind": "statute",
        "title": "قانون آزمایشی",
        "jurisdiction": "IR",
        "source_authority_id": "majles",
        "source_url": "https://example.gov.ir/law.pdf",
        "source_document_sha256": "a" * 64,
        "acquired_at": "2026-11-01T10:00:00+00:00",
        "original_pdf_path": "evidence/original.pdf",
        "extraction_pipeline_version": "3.7.0",
        "extracted_text_sha256": "b" * 64,
        "validation_report_refs": ["11_final_validation_report.json"],
        "review_decision": {"approved": False, "status": "pending"},
        "records": [{
            "record_id": "record-001", "record_kind": "article",
            "parent_document_id": candidate_id, "locator": "ماده ۱",
            "text_original": text, "source_page_refs": [1],
            "record_sha256": hashlib.sha256(text.encode()).hexdigest(),
        }],
    }


def _gate():
    return {"phase5_eligible": True, "active_bank_changed": False, "import_performed": False}


def test_valid_candidate_goes_to_isolated_staging_and_does_not_touch_active_bank(tmp_path):
    active = tmp_path / "laws.json"
    active.write_text('{"قانون": []}', encoding="utf-8")
    before = active.read_bytes()
    result = create_candidate_package(_candidate(), data_dir=tmp_path, final_validation_report=_gate())
    package = Path(result["path"])
    assert result["destination"] == "staging"
    assert result["human_approval_granted"] is False
    assert (package / "candidate.json").is_file()
    assert (package / "records.json").is_file()
    assert json.loads((package / "package_manifest.json").read_text()) ["import_performed"] is False
    assert active.read_bytes() == before


def test_invalid_or_gate_blocked_candidate_is_quarantined(tmp_path):
    candidate = _candidate()
    candidate["records"][0]["record_sha256"] = "c" * 64
    result = create_candidate_package(candidate, data_dir=tmp_path, final_validation_report=_gate())
    assert result["destination"] == "quarantine"
    assert "records[0]:record_sha256_mismatch" in result["validation_errors"]

    result2 = create_candidate_package(_candidate("candidate-002"), data_dir=tmp_path)
    assert result2["destination"] == "quarantine"
    assert result2["phase4_6_gate_passed"] is False


def test_duplicate_ids_are_never_overwritten(tmp_path):
    create_candidate_package(_candidate(), data_dir=tmp_path, final_validation_report=_gate())
    with pytest.raises(FileExistsError):
        create_candidate_package(_candidate(), data_dir=tmp_path, final_validation_report=_gate())


def test_schema_rejects_duplicate_record_ids_and_approved_candidate_decision():
    candidate = _candidate()
    candidate["records"].append(dict(candidate["records"][0]))
    candidate["review_decision"] = {"approved": True}
    result = validate_candidate(candidate)
    assert result["valid"] is False
    assert any("duplicate:record_id" in error for error in result["errors"])
    assert "review_decision_must_remain_pending_or_unapproved" in result["errors"]


def test_five_pipeline_document_kinds_are_accepted_and_targeted():
    from legal_bot.ingestion.controlled_import import KIND_TARGET

    targets = {
        "law": "laws.json",
        "regulation": "samples_and_circulars.json",
        "supreme_court_ruling": "rulings.json",
        "administrative_court_ruling": "rulings.json",
        "advisory_opinion": "consultations.json",
    }
    for kind, target in targets.items():
        candidate = _candidate(f"candidate-{kind.replace('_', '-')}")
        candidate["document_kind"] = kind
        assert validate_candidate(candidate)["valid"], validate_candidate(candidate)["errors"]
        assert KIND_TARGET[kind] == target


def test_invalid_explicit_document_family_is_rejected():
    candidate = _candidate()
    candidate["document_family"] = "some_guessed_family"
    result = validate_candidate(candidate)
    assert not result["valid"]
    assert "invalid:document_family" in result["errors"]
