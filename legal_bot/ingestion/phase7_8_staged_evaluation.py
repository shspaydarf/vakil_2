# -*- coding: utf-8 -*-
"""Phase 7.8: human-approved isolated staging and retrieval evaluation.

This phase evaluates an already quarantined/staged candidate against the
production retrieval scoring primitives without inserting it into the active
corpus, index, or any JSON bank. A 7.7 approval is bound to the candidate and
verified through its append-only decision ledger. This is data-quality and
retrieval evaluation only; it does not establish legal authenticity, current
force, or legal effect.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .. import laws
from .human_review_gate import verify_review_ledger
from .legal_search_preview import preview_staged_package

BANK_FILES = ("laws.json", "rulings.json", "consultations.json", "samples_and_circulars.json")


class Phase78EvaluationError(ValueError):
    """Invalid staged package, review evidence, or evaluation request."""


def _packet_digest(packet: Mapping[str, Any]) -> str:
    payload = {key: value for key, value in packet.items() if key not in {"created_at", "packet_sha256"}}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _sha_bytes(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def active_bank_fingerprint() -> dict[str, str | None]:
    """Fingerprint the four active JSON banks without opening them for writes."""
    root = Path(laws.LAW_FILE).parent
    return {name: _sha_bytes(root / name) for name in BANK_FILES}


def _verify_7_7_approval(candidate: Mapping[str, Any], packet: Mapping[str, Any],
                          ledger: Mapping[str, Any]) -> dict[str, Any]:
    if packet.get("schema_version") != "7.7" or not packet.get("packet_sha256"):
        raise Phase78EvaluationError("valid_phase7_7_review_packet_required")
    if _packet_digest(packet) != packet.get("packet_sha256"):
        raise Phase78EvaluationError("phase7_7_review_packet_integrity_failed")
    if packet.get("status") == "blocked" or packet.get("review_scope") != "ingestion_data_quality_only":
        raise Phase78EvaluationError("review_packet_blocked_or_scope_invalid")
    if packet.get("safety", {}).get("active_bank_write") is not False:
        raise Phase78EvaluationError("review_packet_safety_flags_invalid")
    expected_document_id = str(candidate.get("catalog_document_id") or candidate.get("candidate_id") or "")
    if not expected_document_id or packet.get("document_id") != expected_document_id:
        raise Phase78EvaluationError("review_packet_candidate_identity_mismatch")
    if not verify_review_ledger(dict(ledger)):
        raise Phase78EvaluationError("phase7_7_review_ledger_integrity_failed")
    events = ledger.get("events") or []
    if not events:
        raise Phase78EvaluationError("phase7_7_approval_event_missing")
    approval = events[-1]
    if (approval.get("decision") != "approved_for_staging"
            or approval.get("review_id") != packet.get("review_id")
            or approval.get("document_id") != packet.get("document_id")
            or approval.get("packet_sha256") != packet.get("packet_sha256")
            or approval.get("review_scope") != "ingestion_data_quality_only"):
        raise Phase78EvaluationError("latest_human_decision_is_not_matching_staging_approval")
    if approval.get("legal_validity_determined") is not False or approval.get("active_bank_write") is not False:
        raise Phase78EvaluationError("phase7_7_approval_scope_or_safety_invalid")
    return {"review_id": packet["review_id"], "reviewer_id": approval.get("reviewer_id"),
            "decided_at": approval.get("decided_at"), "decision": approval.get("decision"),
            "packet_sha256": packet.get("packet_sha256"), "ledger_head_sha256": ledger.get("head_sha256")}


def _ranking_metrics(found_ids: list[str], expected_ids: list[str], k: int) -> dict[str, Any]:
    expected = set(expected_ids)
    top = found_ids[:k]
    relevant = [1 if item in expected else 0 for item in top]
    hits = sum(relevant)
    precision = hits / k if k else 0.0
    recall = hits / len(expected) if expected else None
    reciprocal_rank = next((1.0 / (i + 1) for i, item in enumerate(found_ids) if item in expected), 0.0) if expected else None
    dcg = sum(rel / math.log2(index + 2) for index, rel in enumerate(relevant))
    ideal_count = min(len(expected), k)
    idcg = sum(1.0 / math.log2(index + 2) for index in range(ideal_count))
    ndcg = dcg / idcg if idcg else None
    return {"precision_at_k": round(precision, 6), "recall_at_k": round(recall, 6) if recall is not None else None,
            "reciprocal_rank": round(reciprocal_rank, 6) if reciprocal_rank is not None else None,
            "ndcg_at_k": round(ndcg, 6) if ndcg is not None else None,
            "expected_ids_count": len(expected), "matched_expected_ids": [x for x in top if x in expected]}


def evaluate_approved_staging_package(
    package_dir: str | Path,
    queries: Sequence[str],
    *,
    review_packet: Mapping[str, Any],
    review_ledger: Mapping[str, Any],
    expected_record_ids: Mapping[str, Sequence[str]] | None = None,
    limit: int = 10,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """Evaluate retrieval for one human-approved staging package; never activate it."""
    if not queries:
        raise Phase78EvaluationError("at_least_one_query_required")
    if not 1 <= int(limit) <= 20:
        raise Phase78EvaluationError("limit_must_be_between_1_and_20")
    package = Path(package_dir)
    manifest_path, candidate_path = package / "package_manifest.json", package / "candidate.json"
    if not manifest_path.is_file() or not candidate_path.is_file():
        raise FileNotFoundError("staging_package_files_missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    if manifest.get("destination") != "staging" or manifest.get("package_status") != "staged_pending_human_review":
        raise Phase78EvaluationError("candidate_must_remain_in_isolated_staging")
    if manifest.get("active_bank_modified") is not False or manifest.get("import_performed") is not False:
        raise Phase78EvaluationError("staging_manifest_activation_flags_invalid")
    if candidate.get("candidate_id") != manifest.get("candidate_id") or package.name != candidate.get("candidate_id"):
        raise Phase78EvaluationError("staging_candidate_identity_mismatch")
    approval = _verify_7_7_approval(candidate, review_packet, review_ledger)

    before = active_bank_fingerprint()
    baseline_before = {str(q): [(x.get("citation", {}).get("id"), x.get("retrieval_score"))
                                for x in laws.search(str(q), int(limit))] for q in queries}
    preview = preview_staged_package(package, queries, limit=int(limit))
    baseline_after = {str(q): [(x.get("citation", {}).get("id"), x.get("retrieval_score"))
                               for x in laws.search(str(q), int(limit))] for q in queries}
    after = active_bank_fingerprint()

    query_reports = []
    expected_total = matched_total = 0
    for item in preview["queries"]:
        query = item["query"]
        expected = list((expected_record_ids or {}).get(query, []))
        hits = item["hits"]
        found_ids = [str(hit.get("record_id")) for hit in hits if hit.get("record_id") is not None]
        metrics = _ranking_metrics(found_ids, expected, int(limit)) if expected else {
            "precision_at_k": None, "recall_at_k": None, "reciprocal_rank": None,
            "ndcg_at_k": None, "expected_ids_count": 0, "matched_expected_ids": []}
        expected_total += len(expected)
        matched_total += len(metrics["matched_expected_ids"])
        query_reports.append({"query": query, "hit_count": item["hit_count"],
                              "expected_record_ids_assessed": bool(expected), **metrics,
                              "all_hits_have_source_pages": all(bool(hit.get("source_page_refs")) for hit in hits),
                              "all_hits_staging_labelled": all(hit.get("activation_status") == "staging_only_not_active" for hit in hits),
                              "hits": hits})

    bank_unchanged = before == after
    active_search_unchanged = baseline_before == baseline_after
    source_pages_ok = all(row["all_hits_have_source_pages"] for row in query_reports)
    staging_labels_ok = all(row["all_hits_staging_labelled"] for row in query_reports)
    blockers = []
    if not bank_unchanged:
        blockers.append("active_bank_fingerprint_changed")
    if not active_search_unchanged:
        blockers.append("active_search_results_changed")
    if not source_pages_ok:
        blockers.append("search_hit_missing_source_page_reference")
    if not staging_labels_ok:
        blockers.append("search_hit_missing_staging_only_label")
    if expected_total == 0:
        blockers.append("expected_relevance_labels_not_supplied_metrics_not_assessed")

    report = {
        "schema_version": "7.8", "phase": "7.8", "candidate_id": candidate["candidate_id"],
        "document_title": candidate.get("title"), "review_approval": approval,
        "evaluation_status": "completed_with_blockers" if blockers else "completed_metrics_assessed",
        "retrieval_engine": preview.get("retrieval_engine"), "limit": int(limit),
        "query_reports": query_reports,
        "expected_record_recall_at_k": round(matched_total / expected_total, 6) if expected_total else None,
        "expected_record_recall_assessed": expected_total > 0,
        "active_bank_sha256_before": before, "active_bank_sha256_after": after,
        "active_bank_unchanged": bank_unchanged,
        "active_search_results_unchanged": active_search_unchanged,
        "active_bank_modified": False if bank_unchanged else None,
        "active_search_index_modified": False, "import_performed": False,
        "staging_only": True, "blocker_codes": blockers,
        "safety": {"legal_authenticity_confirmed": False, "current_force_confirmed": False,
                   "amendment_or_repeal_confirmed": False, "source_authority_promoted": False,
                   "active_bank_write": False, "network_access": False},
        "limitations": [
            "Only the explicitly supplied human-approved staging candidate was evaluated.",
            "Expected relevance labels must be curated by a human; absent labels mean precision/recall are not assessed.",
            "Retrieval metrics measure ranking against supplied labels, not legal correctness or legal effect.",
            "No records were inserted into the active corpus, search index, or JSON banks.",
            "This report does not authorize a Phase 5.7 commit or production activation.",
        ],
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }
    if output_path is not None:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix(target.suffix + ".tmp")
        temp.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.replace(target)
        report["report_path"] = str(target)
    return report
