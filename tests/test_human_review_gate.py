import json
import pytest

from legal_bot.ingestion.human_review_gate import (
    HumanReviewError, ReviewPolicy, build_review_packet, record_review_decision,
    verify_review_ledger, write_review_artifact,
)


def _document(**overrides):
    doc = {
        "document_id": "doc-1",
        "source_authority_at_discovery": "official_primary",
        "source_evidence": {"reference": "manual-source-verification-001", "reviewer": "reviewer-a"},
        "record": {"title": "قانون نمونه آزمایشی", "source_id": "majlis"},
        "pdf_metadata": {"sha256": "a" * 64, "valid_pdf_signature": True,
                         "structural_validation_passed": True, "original_preserved": True},
        "extraction_metrics": {"page_count": 10, "low_text_pages": 0},
        "ocr_metrics": {"mean_confidence": 0.96},
        "structure": {"articles": [{"number": "1"}, {"number": "2"}]},
    }
    doc.update(overrides)
    return doc


def _approve(packet, ledger=None):
    return record_review_decision(
        packet, ledger, decision="approved_for_staging", reviewer_id="human-1",
        rationale="Original PDF and extracted content manually compared.",
        completed_checklist=packet["checklist_required"],
        evidence_refs=["review-log:case-17", "pdf-page-check:1-10"],
        decided_at="2026-11-01T12:00:00+00:00",
    )


def test_builds_review_packet_with_required_checklist_and_scope():
    packet = build_review_packet(_document())
    assert packet["status"] == "awaiting_human_review"
    assert len(packet["checklist_required"]) == 5
    assert packet["review_scope"] == "ingestion_data_quality_only"
    assert packet["safety"]["legal_validity_determined"] is False


def test_missing_official_source_evidence_blocks_packet():
    packet = build_review_packet(_document(source_evidence=None))
    assert packet["status"] == "blocked"
    assert "OFFICIAL_SOURCE_EVIDENCE_MISSING" in {f["code"] for f in packet["findings"]}


def test_missing_pdf_hash_blocks_packet():
    doc = _document(pdf_metadata={"valid_pdf_signature": True})
    packet = build_review_packet(doc)
    assert packet["status"] == "blocked"
    assert "PDF_HASH_MISSING" in {f["code"] for f in packet["findings"]}


def test_low_ocr_confidence_is_warning_not_legal_finding():
    packet = build_review_packet(_document(ocr_metrics={"mean_confidence": 0.4}))
    finding = next(f for f in packet["findings"] if f["code"] == "LOW_OCR_CONFIDENCE")
    assert finding["severity"] == "warning"


def test_secondary_source_is_never_promoted_by_review_packet():
    packet = build_review_packet(_document(source_authority_at_discovery="secondary"))
    assert packet["source_authority"] == "secondary"
    assert packet["safety"]["source_authority_promoted"] is False


def test_approval_requires_complete_checklist_and_evidence():
    packet = build_review_packet(_document())
    with pytest.raises(HumanReviewError):
        record_review_decision(packet, None, decision="approved_for_staging", reviewer_id="h1",
                               rationale="checked", completed_checklist=[], evidence_refs=["x"])
    with pytest.raises(HumanReviewError):
        record_review_decision(packet, None, decision="approved_for_staging", reviewer_id="h1",
                               rationale="checked", completed_checklist=packet["checklist_required"], evidence_refs=[])


def test_blocked_packet_cannot_be_approved():
    packet = build_review_packet(_document(pdf_metadata={}))
    with pytest.raises(HumanReviewError):
        _approve(packet)


def test_decision_ledger_is_hash_chained_and_append_only():
    packet = build_review_packet(_document())
    first = _approve(packet)
    assert verify_review_ledger(first)
    second = record_review_decision(packet, first, decision="needs_correction", reviewer_id="human-2",
                                    rationale="Please recheck page 4 OCR.", completed_checklist=[],
                                    evidence_refs=["review-note:4"], decided_at="2026-11-01T13:00:00+00:00")
    assert len(second["events"]) == 2
    assert first["events"] == second["events"][:1]
    assert verify_review_ledger(second)


def test_tampered_ledger_fails_verification():
    ledger = _approve(build_review_packet(_document()))
    ledger["events"][0]["rationale"] = "tampered"
    assert not verify_review_ledger(ledger)


def test_graph_relationship_requires_evidence_excerpt():
    graph = {"schema_version": "7.6", "safety": {"all_relationships_are_candidates": True},
             "edges": [{"id": "edge-1", "type": "possible_amends", "evidence": {}}]}
    packet = build_review_packet(_document(), graph=graph)
    assert packet["status"] == "blocked"
    assert "RELATIONSHIP_EVIDENCE_MISSING" in {f["code"] for f in packet["findings"]}


def test_atomic_write_packet_and_ledger(tmp_path):
    packet = build_review_packet(_document())
    packet_path = write_review_artifact(packet, tmp_path / "review" / "packet.json")
    assert json.loads(packet_path.read_text(encoding="utf-8"))["packet_sha256"] == packet["packet_sha256"]
    ledger = _approve(packet)
    ledger_path = write_review_artifact(ledger, tmp_path / "review" / "ledger.json")
    assert verify_review_ledger(json.loads(ledger_path.read_text(encoding="utf-8")))


def test_invalid_policy_and_decision_are_rejected():
    with pytest.raises(HumanReviewError):
        build_review_packet(_document(), policy=ReviewPolicy(min_ocr_confidence=1.5))
    packet = build_review_packet(_document())
    with pytest.raises(HumanReviewError):
        record_review_decision(packet, None, decision="auto_legal_approval", reviewer_id="h1",
                               rationale="x", completed_checklist=[], evidence_refs=[])
