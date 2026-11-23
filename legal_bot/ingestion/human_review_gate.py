# -*- coding: utf-8 -*-
"""Phase 7.7: human review packets and an append-only decision ledger.

This module evaluates ingestion quality and records human decisions. An approval
means only that the specified data-quality review was completed; it never
certifies legal validity, force, amendment, repeal, or official authority.
No network access and no active-bank writes are performed here.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


class HumanReviewError(ValueError):
    """Invalid review packet, decision, or ledger state."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ReviewPolicy:
    min_ocr_confidence: float = 0.85
    max_low_text_pages_ratio: float = 0.20
    require_source_evidence_for_official: bool = True
    max_findings: int = 10000

    def validate(self) -> None:
        if not 0 <= self.min_ocr_confidence <= 1:
            raise HumanReviewError("min_ocr_confidence must be between 0 and 1")
        if not 0 <= self.max_low_text_pages_ratio <= 1:
            raise HumanReviewError("max_low_text_pages_ratio must be between 0 and 1")
        if self.max_findings < 1:
            raise HumanReviewError("max_findings must be positive")


def build_review_packet(document: dict[str, Any], *, graph: dict[str, Any] | None = None,
                       policy: ReviewPolicy | None = None) -> dict[str, Any]:
    """Create a review checklist and findings from caller-supplied pipeline artifacts.

    The function deliberately does not infer official status from a URL/domain.
    Missing evidence is flagged; OCR/structure metrics are treated as quality
    signals, not legal conclusions.
    """
    policy = policy or ReviewPolicy()
    policy.validate()
    if not isinstance(document, dict):
        raise HumanReviewError("document must be an object")
    document_id = str(document.get("document_id", "")).strip()
    record = document.get("record") or {}
    if not document_id or not isinstance(record, dict) or not str(record.get("title", "")).strip():
        raise HumanReviewError("document_id and record.title are required")

    findings: list[dict[str, Any]] = []

    def add(code: str, severity: str, detail: str, evidence: dict[str, Any] | None = None) -> None:
        findings.append({"finding_id": _sha([document_id, code, detail, evidence or {}])[:24],
                         "code": code, "severity": severity, "detail": detail,
                         "evidence": evidence or {}, "resolution_required": severity == "blocker"})
        if len(findings) > policy.max_findings:
            raise HumanReviewError("finding count exceeds policy limit")

    authority = str(document.get("source_authority_at_discovery", document.get("source_authority", "unverified")))
    if authority not in {"official_primary", "secondary", "unverified"}:
        authority = "unverified"
        add("UNKNOWN_AUTHORITY_LABEL", "blocker", "Source authority label is not recognized")
    source_evidence = document.get("source_evidence") or record.get("source_evidence")
    if authority == "official_primary" and policy.require_source_evidence_for_official and not source_evidence:
        add("OFFICIAL_SOURCE_EVIDENCE_MISSING", "blocker",
            "Official-primary designation lacks explicit human-verifiable evidence")
    if authority != "official_primary":
        add("NON_PRIMARY_SOURCE", "warning",
            "Source is secondary or unverified; this review cannot promote its authority",
            {"source_authority": authority})

    pdf = document.get("pdf_metadata") or {}
    if not pdf.get("sha256"):
        add("PDF_HASH_MISSING", "blocker", "Original PDF SHA-256 is missing")
    if pdf.get("valid_pdf_signature") is False or pdf.get("structural_validation_passed") is False:
        add("PDF_INTEGRITY_FAILED", "blocker", "PDF integrity validation failed")
    if pdf.get("original_preserved") is False:
        add("ORIGINAL_PDF_NOT_PRESERVED", "blocker", "Original PDF preservation is not confirmed")

    extraction = document.get("extraction_metrics") or {}
    page_count = extraction.get("page_count")
    low_text_pages = extraction.get("low_text_pages")
    if isinstance(page_count, int) and page_count > 0 and isinstance(low_text_pages, int) and low_text_pages >= 0:
        ratio = low_text_pages / page_count
        if ratio > policy.max_low_text_pages_ratio:
            add("MANY_LOW_TEXT_PAGES", "warning", "A notable share of pages has little extracted text",
                {"page_count": page_count, "low_text_pages": low_text_pages, "ratio": ratio})
    ocr = document.get("ocr_metrics") or {}
    confidence = ocr.get("mean_confidence")
    if confidence is not None:
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            add("INVALID_OCR_CONFIDENCE", "blocker", "OCR confidence metric is not numeric")
        else:
            if not 0 <= confidence <= 1:
                add("INVALID_OCR_CONFIDENCE", "blocker", "OCR confidence is outside the 0..1 range")
            elif confidence < policy.min_ocr_confidence:
                add("LOW_OCR_CONFIDENCE", "warning", "OCR confidence is below the review threshold",
                    {"mean_confidence": confidence, "threshold": policy.min_ocr_confidence})
    elif document.get("ocr_used"):
        add("OCR_CONFIDENCE_MISSING", "warning", "OCR was used but no confidence metric was supplied")

    structure = document.get("structure") or {}
    articles = structure.get("articles", []) or []
    article_numbers = [str(a.get("number", "")).strip() for a in articles if isinstance(a, dict)]
    if not articles:
        add("NO_ARTICLES_PARSED", "warning", "No article structure was supplied; visual/text review is required")
    if len(article_numbers) != len(set(article_numbers)):
        add("DUPLICATE_ARTICLE_NUMBERS", "warning", "Repeated article numbers were detected",
            {"article_numbers": article_numbers})
    for index, article in enumerate(articles):
        if not isinstance(article, dict) or not str(article.get("number", "")).strip():
            add("MALFORMED_ARTICLE", "blocker", "An article has no valid article number", {"index": index})

    graph_info: dict[str, Any] = {"provided": graph is not None, "edge_count": 0, "candidate_relationships": 0}
    if graph is not None:
        if graph.get("schema_version") != "7.6" or not graph.get("safety", {}).get("all_relationships_are_candidates"):
            add("UNSAFE_OR_UNKNOWN_GRAPH", "blocker", "Relationship graph is not a recognized review-only 7.6 graph")
        else:
            edges = graph.get("edges", []) or []
            graph_info.update({"edge_count": len(edges),
                               "candidate_relationships": sum(e.get("type") not in {"contains_article", "contains_note", "contains_band", "contains_subitem"} for e in edges)})
            for edge in edges:
                if edge.get("type") in {"possible_amends", "possible_repeals"} and not edge.get("evidence", {}).get("excerpt"):
                    add("RELATIONSHIP_EVIDENCE_MISSING", "blocker",
                        "A possible amendment/repeal edge has no supporting excerpt", {"edge_id": edge.get("id")})

    checklist = [
        "source_identity_checked", "original_pdf_visually_checked", "text_and_ocr_checked",
        "article_structure_checked", "references_and_relationships_checked",
    ]
    packet = {
        "schema_version": "7.7", "review_id": _sha([document_id, record.get("title"), _sha(findings), _sha(checklist)])[:24],
        "document_id": document_id, "title": str(record["title"]),
        "review_scope": "ingestion_data_quality_only", "source_authority": authority,
        "findings": findings, "checklist_required": checklist,
        "graph": graph_info,
        "status": "blocked" if any(f["severity"] == "blocker" for f in findings) else "awaiting_human_review",
        "created_at": _utc_now(),
        "safety": {"legal_validity_determined": False, "force_or_effect_determined": False,
                   "amendment_or_repeal_legally_confirmed": False, "source_authority_promoted": False,
                   "network_access": False, "active_bank_write": False},
    }
    packet["packet_sha256"] = _sha({k: v for k, v in packet.items() if k not in {"created_at", "packet_sha256"}})
    return packet


def record_review_decision(packet: dict[str, Any], ledger: dict[str, Any] | None, *,
                           decision: str, reviewer_id: str, rationale: str,
                           completed_checklist: Iterable[str], evidence_refs: Iterable[str],
                           decided_at: str | None = None) -> dict[str, Any]:
    """Append one human decision to a hash-chained ledger; never edits prior events."""
    if packet.get("schema_version") != "7.7" or not packet.get("packet_sha256"):
        raise HumanReviewError("a valid 7.7 review packet is required")
    if decision not in {"approved_for_staging", "rejected", "needs_correction"}:
        raise HumanReviewError("unsupported decision")
    reviewer_id = str(reviewer_id or "").strip()
    rationale = str(rationale or "").strip()
    if not reviewer_id or not rationale:
        raise HumanReviewError("reviewer_id and rationale are required")
    try:
        timestamp = datetime.fromisoformat(decided_at) if decided_at else datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            raise ValueError
        timestamp = timestamp.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        raise HumanReviewError("decided_at must be a timezone-aware ISO timestamp")

    required = set(packet.get("checklist_required", []))
    completed = set(str(x) for x in completed_checklist)
    evidence = sorted(set(str(x).strip() for x in evidence_refs if str(x).strip()))
    if decision == "approved_for_staging":
        if packet.get("status") == "blocked" or any(f.get("severity") == "blocker" for f in packet.get("findings", [])):
            raise HumanReviewError("blocked packet cannot be approved; resolve blockers and create a corrected packet")
        if not required.issubset(completed):
            raise HumanReviewError("all required review checklist items must be completed")
        if not evidence:
            raise HumanReviewError("approval requires at least one evidence reference")
    if decision in {"rejected", "needs_correction"} and not rationale:
        raise HumanReviewError("rejection/correction requires rationale")

    current = ledger or {"schema_version": "7.7", "events": [], "head_sha256": "0" * 64}
    if current.get("schema_version") != "7.7" or not isinstance(current.get("events"), list):
        raise HumanReviewError("invalid review ledger")
    previous = current.get("head_sha256", "0" * 64)
    expected_previous = current["events"][-1].get("event_sha256") if current["events"] else "0" * 64
    if previous != expected_previous:
        raise HumanReviewError("ledger hash-chain head mismatch")
    event = {"event_id": _sha([packet["review_id"], reviewer_id, timestamp, decision, previous])[:24],
             "review_id": packet["review_id"], "document_id": packet["document_id"],
             "packet_sha256": packet["packet_sha256"], "decision": decision,
             "reviewer_id": reviewer_id, "rationale": rationale,
             "completed_checklist": sorted(completed), "evidence_refs": evidence,
             "decided_at": timestamp, "review_scope": "ingestion_data_quality_only",
             "previous_event_sha256": previous,
             "legal_validity_determined": False, "active_bank_write": False}
    event["event_sha256"] = _sha(event)
    return {"schema_version": "7.7", "events": current["events"] + [event],
            "head_sha256": event["event_sha256"],
            "safety": {"append_only": True, "legal_validity_determined": False,
                       "source_authority_promoted": False, "active_bank_write": False}}


def verify_review_ledger(ledger: dict[str, Any]) -> bool:
    """Verify event hashes, ordering, and chain links."""
    if ledger.get("schema_version") != "7.7" or not isinstance(ledger.get("events"), list):
        return False
    previous = "0" * 64
    for event in ledger["events"]:
        if event.get("previous_event_sha256") != previous:
            return False
        payload = {k: v for k, v in event.items() if k != "event_sha256"}
        digest = _sha(payload)
        if event.get("event_sha256") != digest:
            return False
        previous = digest
    return ledger.get("head_sha256", "0" * 64) == previous


def write_review_artifact(artifact: dict[str, Any], output_path: str | Path) -> Path:
    """Atomically write only 7.7 review packets or ledgers to a caller-chosen path."""
    if artifact.get("schema_version") != "7.7":
        raise HumanReviewError("only schema 7.7 artifacts may be written")
    if "events" in artifact and not verify_review_ledger(artifact):
        raise HumanReviewError("review ledger integrity check failed")
    if "review_id" in artifact and not artifact.get("packet_sha256"):
        raise HumanReviewError("review packet hash is missing")
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(artifact, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temp_path, target)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
    return target
