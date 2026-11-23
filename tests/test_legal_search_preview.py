import hashlib
import json
from pathlib import Path

import pytest

from legal_bot.ingestion.staging_packages import create_candidate_package
from legal_bot.ingestion.legal_search_preview import preview_staged_package


def _candidate(candidate_id="preview-001"):
    text = "ماده ۱ ـ هرگاه متعهد از انجام تعهد قراردادی خودداری کند، مسئول جبران خسارت است."
    return {
        "candidate_id": candidate_id, "document_kind": "statute", "title": "قانون آزمایشی مسئولیت قراردادی",
        "jurisdiction": "IR", "source_authority_id": "majles", "source_url": "https://example.gov.ir/test.pdf",
        "source_document_sha256": "a" * 64, "acquired_at": "2026-11-01T10:00:00+00:00",
        "original_pdf_path": "evidence/original.pdf", "extraction_pipeline_version": "3.7.0",
        "extracted_text_sha256": "b" * 64, "validation_report_refs": ["11_final_validation_report.json"],
        "review_decision": {"approved": False, "status": "pending"},
        "records": [{"record_id": "record-001", "record_kind": "article", "parent_document_id": candidate_id,
                     "locator": "ماده ۱", "text_original": text, "source_page_refs": [2],
                     "record_sha256": hashlib.sha256(text.encode()).hexdigest()}],
    }


def _gate():
    return {"phase5_eligible": True, "active_bank_changed": False, "import_performed": False}


def test_staged_preview_finds_record_using_production_retrieval_scoring(tmp_path):
    package = create_candidate_package(_candidate(), data_dir=tmp_path, final_validation_report=_gate())
    result = preview_staged_package(package["path"], ["مسئول جبران خسارت تعهد قراردادی"])
    assert result["queries"][0]["hit_count"] == 1
    hit = result["queries"][0]["hits"][0]
    assert hit["kind"] == "law"
    assert hit["source_page_refs"] == [2]
    assert hit["activation_status"] == "staging_only_not_active"
    assert result["active_bank_modified"] is False
    assert result["active_search_index_modified"] is False


def test_preview_does_not_change_active_search_results_or_bank_files(tmp_path):
    from legal_bot import laws
    data_dir = Path(laws.LAW_FILE).parent
    names = ["laws.json", "rulings.json", "consultations.json", "samples_and_circulars.json"]
    before = {name: (data_dir / name).read_bytes() for name in names if (data_dir / name).exists()}
    baseline = [(x.get("citation", {}).get("id"), x.get("retrieval_score")) for x in laws.search("مسئولیت مدنی", 5)]
    package = create_candidate_package(_candidate("preview-002"), data_dir=tmp_path, final_validation_report=_gate())
    preview_staged_package(package["path"], ["مسئولیت قراردادی"])
    after = [(x.get("citation", {}).get("id"), x.get("retrieval_score")) for x in laws.search("مسئولیت مدنی", 5)]
    assert baseline == after
    assert before == {name: (data_dir / name).read_bytes() for name in before}


def test_quarantine_package_cannot_be_previewed(tmp_path):
    candidate = _candidate("preview-003")
    candidate["records"][0]["record_sha256"] = "c" * 64
    package = create_candidate_package(candidate, data_dir=tmp_path, final_validation_report=_gate())
    assert package["destination"] == "quarantine"
    with pytest.raises(ValueError, match="staging_package"):
        preview_staged_package(package["path"], ["مسئولیت"])


def test_preview_rejects_short_queries(tmp_path):
    package = create_candidate_package(_candidate("preview-004"), data_dir=tmp_path, final_validation_report=_gate())
    with pytest.raises(ValueError, match="2_and_200"):
        preview_staged_package(package["path"], ["x"])
