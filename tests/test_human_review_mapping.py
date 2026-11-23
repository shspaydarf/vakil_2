from legal_bot.ingestion.human_review_mapping import prepare_human_review_packet, finalize_human_review


def test_packet_blocks_without_official_pdf_and_extraction():
    packet = prepare_human_review_packet(
        acquisition_manifest={"candidate_id": "C1", "document_title": "قانون", "acquisition_status": "blocked", "mirror_fallback_used": False},
        technical_validation_report={"technical_integrity_passed": False, "validation_status": "blocked_pending_official_pdf"},
    )
    assert packet["packet_status"] == "blocked_pending_official_pdf_and_extraction"
    assert "original_official_pdf_unavailable" in packet["reason_codes"]
    assert packet["active_bank_modified"] is False


def test_packet_ready_only_with_real_pdf_and_63_pass(tmp_path):
    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(b"%PDF-1.4\nfixture")
    packet = prepare_human_review_packet(
        acquisition_manifest={"candidate_id": "C1", "document_title": "قانون", "acquisition_status": "downloaded_pending_integrity_review", "original_pdf": str(pdf), "sha256": "abc", "final_source_url": "https://rc.majlis.ir/file.pdf", "mirror_fallback_used": False},
        technical_validation_report={"technical_integrity_passed": True, "validation_status": "technical_integrity_passed_pending_human_legal_review", "legal_authenticity_confirmed": False},
        extracted_structure={"articles": []},
    )
    assert packet["packet_status"] == "ready_for_human_review"


def test_approved_decision_requires_mapping_and_preserves_content():
    packet = {"packet_status": "ready_for_human_review", "packet_sha256": "x", "active_bank_modified": False}
    decision = {"reviewer_id": "reviewer-1", "decided_at": "2026-11-01T00:00:00Z", "decision": "approved_for_mapping", "compared_with_original_pdf": True, "reviewed_page_ranges": [{"start": 1, "end": 2}]}
    out = finalize_human_review(packet, decision=decision)
    assert out["review_status"] == "blocked_pending_review_correction"
    assert "explicit_bank_mapping_required" in out["reason_codes"]


def test_valid_review_and_mapping_never_write_active_bank():
    packet = {"packet_status": "ready_for_human_review", "packet_sha256": "x"}
    decision = {"reviewer_id": "reviewer-1", "decided_at": "2026-11-01T00:00:00Z", "decision": "approved_for_mapping", "compared_with_original_pdf": True, "reviewed_page_ranges": [{"start": 1, "end": 2}]}
    mapping = {"target_collection": "laws", "field_map": {"title": "title", "articles": "articles"}, "record_mappings": [{"source_record_id": "a1", "target_record_id": "law-a1"}], "reviewer_id": "reviewer-1", "drop_unmapped_content": False, "overwrite_existing": False}
    out = finalize_human_review(packet, decision=decision, mapping=mapping)
    assert out["review_status"] == "human_review_recorded"
    assert out["active_bank_modified"] is False


def test_mapping_rejects_overwrite_or_dropped_content():
    packet = {"packet_status": "ready_for_human_review", "packet_sha256": "x"}
    decision = {"reviewer_id": "r", "decided_at": "now", "decision": "approved_for_mapping", "compared_with_original_pdf": True, "reviewed_page_ranges": [1]}
    mapping = {"target_collection": "laws", "field_map": {"title": "title"}, "record_mappings": [1], "reviewer_id": "r", "drop_unmapped_content": True, "overwrite_existing": True}
    out = finalize_human_review(packet, decision=decision, mapping=mapping)
    assert "dropping_unmapped_content_not_allowed" in out["reason_codes"]
    assert "overwrite_existing_not_allowed" in out["reason_codes"]
