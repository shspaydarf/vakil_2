# -*- coding: utf-8 -*-
"""Phase 6.5: isolated staged-search evaluation and operational readiness gate.

This phase evaluates retrieval compatibility only. It never imports records,
changes the active corpus/index, or establishes legal authenticity/current force.
A synthetic fixture may test the evaluator, but cannot satisfy the real-document
readiness gate.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .. import laws
from .legal_search_preview import preview_staged_package

BANK_FILES = ("laws.json", "rulings.json", "consultations.json", "samples_and_circulars.json")


def _sha(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _active_bank_fingerprint() -> dict[str, str | None]:
    root = Path(laws.LAW_FILE).parent
    return {name: _sha(root / name) for name in BANK_FILES}


def _human_review_passed(review: Mapping[str, Any] | None) -> bool:
    if not isinstance(review, Mapping):
        return False
    decision = review.get("human_decision") or review.get("decision")
    if not isinstance(decision, Mapping):
        return False
    return (
        decision.get("decision") == "approved_for_mapping"
        and decision.get("compared_with_original_pdf") is True
        and bool(decision.get("reviewer_id"))
        and bool(decision.get("decided_at"))
        and review.get("review_status", "human_review_recorded") == "human_review_recorded"
        and isinstance(review.get("bank_mapping"), Mapping)
    )


def evaluate_staged_candidate(
    package_dir: str | Path,
    queries: Sequence[str],
    *,
    expected_record_ids: Mapping[str, Sequence[str]] | None = None,
    official_pdf_validation: Mapping[str, Any] | None = None,
    human_review: Mapping[str, Any] | None = None,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """Run staged-only search evaluation and report real-document readiness.

    expected_record_ids maps each query to record IDs that should be retrieved.
    If omitted, recall is reported as not assessed rather than guessed.
    """
    if not queries:
        raise ValueError("at_least_one_evaluation_query_required")
    before = _active_bank_fingerprint()
    baseline_search = [
        (item.get("citation", {}).get("id"), item.get("retrieval_score"))
        for item in laws.search(str(queries[0]), 10)
    ]
    preview = preview_staged_package(package_dir, queries, limit=20)
    after = _active_bank_fingerprint()
    baseline_search_after = [
        (item.get("citation", {}).get("id"), item.get("retrieval_score"))
        for item in laws.search(str(queries[0]), 10)
    ]

    candidate_path = Path(package_dir) / "candidate.json"
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    query_reports = []
    total_expected = 0
    total_found = 0
    for item in preview["queries"]:
        q = item["query"]
        expected = list((expected_record_ids or {}).get(q, []))
        found = {hit.get("record_id") for hit in item["hits"]}
        matched = [record_id for record_id in expected if record_id in found]
        total_expected += len(expected)
        total_found += len(matched)
        query_reports.append({
            "query": q,
            "hit_count": item["hit_count"],
            "expected_record_ids": expected,
            "matched_expected_record_ids": matched,
            "expected_recall": (len(matched) / len(expected)) if expected else None,
            "all_hits_have_source_pages": all(bool(hit.get("source_page_refs")) for hit in item["hits"]),
            "all_hits_staging_labelled": all(hit.get("activation_status") == "staging_only_not_active" for hit in item["hits"]),
        })

    pdf_pass = bool(
        isinstance(official_pdf_validation, Mapping)
        and official_pdf_validation.get("technical_integrity_passed") is True
        and official_pdf_validation.get("legal_authenticity_confirmed") is not True
        and official_pdf_validation.get("current_force_confirmed") is not True
    )
    human_pass = _human_review_passed(human_review)
    bank_unchanged = before == after
    search_unchanged = baseline_search == baseline_search_after
    provenance_ok = all(row["all_hits_have_source_pages"] for row in query_reports)
    staging_labels_ok = all(row["all_hits_staging_labelled"] for row in query_reports)
    recall = (total_found / total_expected) if total_expected else None

    blockers = []
    if not pdf_pass:
        blockers.append("real_official_pdf_technical_validation_not_passed")
    if not human_pass:
        blockers.append("human_review_and_explicit_mapping_not_approved")
    if not bank_unchanged:
        blockers.append("active_bank_fingerprint_changed_during_preview")
    if not search_unchanged:
        blockers.append("active_search_results_changed_during_preview")
    if not provenance_ok:
        blockers.append("one_or_more_hits_missing_source_page_references")
    if not staging_labels_ok:
        blockers.append("one_or_more_hits_missing_staging_only_label")

    report = {
        "phase": "6.5",
        "candidate_id": candidate.get("candidate_id"),
        "document_title": candidate.get("title"),
        "evaluation_status": "evaluation_complete_real_document_gate_blocked" if blockers else "ready_for_separate_manual_activation_decision",
        "retrieval_engine": preview.get("retrieval_engine"),
        "query_reports": query_reports,
        "expected_record_recall": recall,
        "expected_record_recall_assessed": total_expected > 0,
        "official_pdf_technical_validation_passed": pdf_pass,
        "human_review_and_mapping_passed": human_pass,
        "active_bank_unchanged": bank_unchanged,
        "active_search_results_unchanged": search_unchanged,
        "active_bank_sha256_before": before,
        "active_bank_sha256_after": after,
        "active_bank_modified": False if bank_unchanged else None,
        "active_search_index_modified": False if search_unchanged else None,
        "import_performed": False,
        "legal_authenticity_confirmed": False,
        "current_force_confirmed": False,
        "blocker_codes": blockers,
        "limitations": [
            "search preview is isolated and does not add staged records to the active corpus",
            "retrieval success does not establish legal correctness, authenticity, amendment status, or current force",
            "synthetic fixture results are software tests, not evidence about the selected real statute",
            "phase 6.5 does not commit or authorize a phase 5.7 import",
        ],
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }
    if output_path is not None:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        report["report_path"] = str(target)
        temp = target.with_suffix(target.suffix + ".tmp")
        temp.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.replace(target)
    return report
