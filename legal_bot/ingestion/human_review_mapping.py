# -*- coding: utf-8 -*-
"""Phase 6.4: human review packet and explicit bank-schema mapping.

This module does not perform legal review or infer legal force. It prepares an
immutable review packet and accepts only explicit, attributable human decisions.
No active-bank writes are performed in Phase 6.4.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _digest(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def prepare_human_review_packet(
    *,
    acquisition_manifest: dict[str, Any],
    technical_validation_report: dict[str, Any],
    extracted_structure: dict[str, Any] | None = None,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """Create a review packet; blocked unless the official PDF passed 6.3."""
    reasons: list[str] = []
    if technical_validation_report.get("technical_integrity_passed") is not True:
        reasons.append("phase6_3_technical_integrity_not_passed")
    if technical_validation_report.get("legal_authenticity_confirmed") is True:
        # 6.3 is not allowed to assert this; treat such a report as invalid.
        reasons.append("phase6_3_overclaimed_legal_authenticity")
    pdf_path = acquisition_manifest.get("original_pdf")
    if not pdf_path or not Path(pdf_path).is_file():
        reasons.append("original_official_pdf_unavailable")
    if acquisition_manifest.get("mirror_fallback_used") is not False:
        reasons.append("mirror_fallback_not_permitted")
    if extracted_structure is None:
        reasons.append("extracted_structure_not_available")

    packet: dict[str, Any] = {
        "phase": "6.4",
        "packet_status": "ready_for_human_review" if not reasons else "blocked_pending_official_pdf_and_extraction",
        "candidate_id": acquisition_manifest.get("candidate_id"),
        "document_title": acquisition_manifest.get("document_title"),
        "official_source_url": acquisition_manifest.get("final_source_url"),
        "original_pdf": pdf_path,
        "original_pdf_sha256": acquisition_manifest.get("sha256"),
        "technical_validation_status": technical_validation_report.get("validation_status"),
        "technical_integrity_passed": technical_validation_report.get("technical_integrity_passed") is True,
        "extracted_structure_sha256": _digest(extracted_structure) if extracted_structure is not None else None,
        "review_requirements": [
            "compare_every_extracted_page_with_the_original_pdf",
            "record_reviewed_page_ranges_and_unreadable_pages",
            "verify_title_dates_numbers_authority_and_document_type_against_original",
            "verify_article_paragraph_clause_and_note_boundaries_against_original",
            "record_every_omission_insertion_or_ocr_uncertainty",
            "do_not_infer_amendment_repeal_or_current_force_without_separate_official_evidence",
            "prepare_explicit_target_bank_mapping_without_dropping_source_content",
        ],
        "reason_codes": reasons,
        "human_decision": None,
        "bank_mapping": None,
        "active_bank_modified": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    packet["packet_sha256"] = _digest(packet)
    if output_path is not None:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix(target.suffix + ".tmp")
        temp.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(target)
        packet["packet_path"] = str(target)
    return packet


def finalize_human_review(
    packet: dict[str, Any],
    *,
    decision: dict[str, Any],
    mapping: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record a human decision and reviewed mapping; never imports into bank."""
    result = dict(packet)
    errors: list[str] = []
    if packet.get("packet_status") != "ready_for_human_review":
        errors.append("review_packet_not_ready")
    required = ("reviewer_id", "decided_at", "decision", "compared_with_original_pdf", "reviewed_page_ranges")
    for key in required:
        if not decision.get(key):
            errors.append(f"missing_{key}")
    if decision.get("compared_with_original_pdf") is not True:
        errors.append("original_pdf_comparison_not_confirmed")
    if decision.get("decision") not in {"approved_for_mapping", "rejected", "needs_correction"}:
        errors.append("invalid_human_decision")
    if not isinstance(decision.get("reviewed_page_ranges"), list) or not decision.get("reviewed_page_ranges"):
        errors.append("reviewed_page_ranges_required")

    if decision.get("decision") == "approved_for_mapping":
        if not isinstance(mapping, dict):
            errors.append("explicit_bank_mapping_required")
        else:
            for key in ("target_collection", "field_map", "record_mappings", "reviewer_id"):
                if not mapping.get(key):
                    errors.append(f"mapping_missing_{key}")
            if mapping.get("reviewer_id") != decision.get("reviewer_id"):
                errors.append("mapping_reviewer_mismatch")
            if mapping.get("drop_unmapped_content") is not False:
                errors.append("dropping_unmapped_content_not_allowed")
            if mapping.get("overwrite_existing") is not False:
                errors.append("overwrite_existing_not_allowed")

    result["human_decision"] = decision
    result["bank_mapping"] = mapping if not errors else None
    result["review_status"] = "human_review_recorded" if not errors else "blocked_pending_review_correction"
    result["reason_codes"] = errors
    result["active_bank_modified"] = False
    result["finalized_at"] = datetime.now(timezone.utc).isoformat()
    result["review_record_sha256"] = _digest({"packet_sha256": packet.get("packet_sha256"), "decision": decision, "mapping": mapping if not errors else None})
    return result
