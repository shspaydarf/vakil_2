import hashlib
import json
from pathlib import Path

from legal_bot.ingestion.record_identity import build_identity_manifest, normalize_identity_text, validate_lineage
from legal_bot.ingestion.staging_packages import create_candidate_package


def _candidate(cid, text="متن ماده"):
    return {
        "candidate_id": cid, "document_kind": "statute", "title": "قانون آزمایشی",
        "jurisdiction": "IR", "source_authority_id": "majles", "source_url": "https://example.gov.ir/a.pdf",
        "source_document_sha256": ("a" if cid.endswith("1") else "b") * 64,
        "acquired_at": "2026-11-01T10:00:00+00:00", "original_pdf_path": "evidence/a.pdf",
        "extraction_pipeline_version": "3.7.0", "extracted_text_sha256": "c" * 64,
        "validation_report_refs": ["11_final_validation_report.json"],
        "review_decision": {"approved": False, "status": "pending"},
        "records": [{"record_id": f"record-{cid}", "record_kind": "article", "parent_document_id": cid,
                     "locator": "ماده ۱", "text_original": text, "source_page_refs": [1],
                     "record_sha256": hashlib.sha256(text.encode()).hexdigest()}],
    }


def _gate():
    return {"phase5_eligible": True, "active_bank_changed": False, "import_performed": False}


def test_persian_identity_normalization_is_stable():
    assert normalize_identity_text("ماده ۱  كيان") == normalize_identity_text("ماده 1 کیان")


def test_family_identity_stable_across_pdf_versions_but_version_identity_changes():
    a = build_identity_manifest(_candidate("candidate-1"))
    b = build_identity_manifest(_candidate("candidate-2"))
    assert a["document_family_id"] == b["document_family_id"]
    assert a["document_version_id"] != b["document_version_id"]
    assert a["records"][0]["logical_record_id"] == b["records"][0]["logical_record_id"]


def test_lineage_requires_explicit_human_reviewer_and_never_confirms_legal_effect():
    good = validate_lineage({"lineage_relations": [{"source_document_id": "old", "target_document_id": "new", "relation_type": "amends", "reviewer_id": "reviewer-1"}]})
    assert good["valid"] and good["relations"][0]["legal_effect_confirmed"] is False
    bad = validate_lineage({"lineage_relations": [{"source_document_id": "old", "target_document_id": "new", "relation_type": "amends"}]})
    assert not bad["valid"]


def test_package_writes_identity_and_duplicate_reports_without_merging(tmp_path):
    first = _candidate("candidate-1")
    create_candidate_package(first, data_dir=tmp_path, final_validation_report=_gate())
    second = _candidate("candidate-2")
    result = create_candidate_package(second, data_dir=tmp_path, final_validation_report=_gate())
    package = Path(result["path"])
    identity = json.loads((package / "identity_manifest.json").read_text())
    duplicate = json.loads((package / "duplicate_report.json").read_text())
    assert identity["automatic_merge_performed"] is False
    assert any(x["match_type"] == "exact_normalized_content" for x in duplicate["matches"])
    assert (package / "lineage_report.json").is_file()
    assert result["automatic_merge_performed"] is False


def test_invalid_explicit_lineage_routes_candidate_to_quarantine(tmp_path):
    candidate = _candidate("candidate-1")
    candidate["lineage_relations"] = [{"source_document_id": "old", "target_document_id": "new", "relation_type": "amends"}]
    result = create_candidate_package(candidate, data_dir=tmp_path, final_validation_report=_gate())
    assert result["destination"] == "quarantine"
    assert "lineage[0]:reviewer_required" in result["lineage_errors"]


def test_official_number_keeps_family_identity_when_title_changes():
    a = _candidate("candidate-1")
    b = _candidate("candidate-2")
    a.update(document_kind="statute", document_number="۱۲۳۴", title="قانون نمونه")
    b.update(document_kind="law", document_number="1234", title="عنوان اصلاح‌شده")
    assert build_identity_manifest(a)["document_family_id"] == build_identity_manifest(b)["document_family_id"]


def test_unknown_generic_kind_and_missing_identity_anchor_do_not_get_family_id():
    candidate = _candidate("candidate-1")
    candidate["document_kind"] = "ruling"
    assert build_identity_manifest(candidate)["document_family_id"] is None
    candidate["document_kind"] = "statute"
    candidate["title"] = ""
    candidate.pop("document_number", None)
    assert build_identity_manifest(candidate)["document_family_id"] is None


def test_empty_record_locator_does_not_get_logical_or_version_id():
    candidate = _candidate("candidate-1")
    candidate["records"][0]["locator"] = "  "
    record = build_identity_manifest(candidate)["records"][0]
    assert record["identity_status"] == "incomplete"
    assert record["logical_record_id"] is None
    assert record["version_record_id"] is None


def test_identity_manifest_keeps_hashes_and_legal_dates_separate():
    candidate = _candidate("candidate-1")
    candidate.update(
        extracted_text="متن خام  ي",
        adoption_date="1400-01-01",
        publication_date="1400-02-01",
        promulgation_date="1400-03-01",
        effective_date="1400-04-01",
    )
    manifest = build_identity_manifest(candidate)
    assert manifest["source_document_sha256"] == candidate["source_document_sha256"]
    assert manifest["extracted_text_sha256"] == candidate["extracted_text_sha256"]
    assert manifest["raw_extracted_text_sha256"] != manifest["normalized_text_sha256"]
    assert manifest["legal_dates"]["adoption_date"] == "1400-01-01"
    assert manifest["legal_dates"]["effective_date"] == "1400-04-01"


def test_all_five_explicit_families_are_canonicalized():
    from legal_bot.ingestion.record_identity import canonical_document_family
    expected = {
        "statute": "laws",
        "regulation": "regulations_and_bylaws",
        "supreme_court_unity_ruling": "supreme_court_unity_rulings",
        "administrative_justice_general_assembly_ruling": "administrative_justice_general_assembly_rulings",
        "judiciary_advisory_opinion": "judiciary_advisory_opinions",
    }
    for source, family in expected.items():
        assert canonical_document_family(source) == family


def test_validate_lineage_rejects_unhashable_fields_without_crashing():
    result = validate_lineage({"lineage_relations": [{
        "source_document_id": [], "target_document_id": "target",
        "relation_type": ["amends"], "reviewer_id": "reviewer",
    }]})
    assert not result["valid"]
    assert "lineage[0]:invalid_source_document_id" in result["errors"]
    assert "lineage[0]:invalid_relation_type" in result["errors"]
    assert result["relations"] == []


def test_incomplete_records_do_not_match_each_other_during_duplicate_scan(tmp_path):
    import json
    from legal_bot.ingestion.record_identity import scan_existing_identities

    root = Path(tmp_path) / "ingestion" / "staging" / "old-candidate"
    root.mkdir(parents=True)
    old = _candidate("old-candidate")
    old["records"][0]["locator"] = ""
    (root / "candidate.json").write_text(json.dumps(old), encoding="utf-8")

    current = _candidate("new-candidate")
    current["source_document_sha256"] = "d" * 64
    current["records"][0]["locator"] = ""
    result = scan_existing_identities(current, tmp_path)
    assert result["matches"] == []


def test_broad_ruling_kind_requires_explicit_specific_family_metadata():
    candidate = _candidate("candidate-1")
    candidate["document_kind"] = "supreme_court_ruling"
    assert build_identity_manifest(candidate)["document_family_id"] is None
    candidate["document_family"] = "supreme_court_unity_rulings"
    assert build_identity_manifest(candidate)["document_family"] == "supreme_court_unity_rulings"
    assert build_identity_manifest(candidate)["document_family_id"] is not None

    candidate["document_kind"] = "administrative_court_ruling"
    candidate["document_family"] = "administrative_justice_general_assembly_rulings"
    assert build_identity_manifest(candidate)["document_family_id"] is not None
