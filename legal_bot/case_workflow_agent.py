"""Supervised, deterministic case-workflow orchestration.

This agent coordinates existing local search and multi-document analysis only.
It does not contact external models, file documents, send messages, or make legal
conclusions. The caller must pass documents already authorized for one case.
Every consequential transition requires an explicit lawyer approval.
"""
from __future__ import annotations
from copy import deepcopy
from typing import Any

from .analysis import search_case_documents
from .cross_document_analysis import analyze_case_documents

WORKFLOW_VERSION = 1
_STEPS = ("search", "extract_compare", "lawyer_review", "complete")


def create_case_workflow(case_id: int, query: str = "") -> dict[str, Any]:
    """Create a JSON-serializable workflow checkpoint; no work is run yet."""
    return {
        "workflow_version": WORKFLOW_VERSION,
        "case_id": int(case_id),
        "status": "PENDING_APPROVAL",
        "current_step": "search",
        "query": str(query or "").strip()[:300],
        "completed_steps": [],
        "approvals": {},
        "results": {},
        "requires_lawyer_review": True,
    }


def approve_step(state: dict[str, Any], step: str, *, approved: bool) -> dict[str, Any]:
    """Record an explicit approval/decline for the current workflow step."""
    current = str((state or {}).get("current_step") or "")
    if current not in _STEPS or step != current:
        raise ValueError("فقط مرحله فعلی گردش کار قابل تأیید است.")
    updated = deepcopy(state)
    updated.setdefault("approvals", {})[step] = bool(approved)
    if not approved:
        updated["status"] = "PAUSED_BY_LAWYER"
        return updated
    updated["status"] = "APPROVED_TO_RUN"
    return updated


def run_approved_step(state: dict[str, Any], documents: list[dict[str, Any]]) -> dict[str, Any]:
    """Run one approved local step and return an updated checkpoint.

    ``documents`` must already be scoped to the case and user by the caller.
    No cross-case database lookup is performed in this pure orchestration layer.
    """
    updated = deepcopy(state or {})
    step = str(updated.get("current_step") or "")
    if updated.get("status") != "APPROVED_TO_RUN" or not updated.get("approvals", {}).get(step):
        raise PermissionError("اجرای این مرحله به تأیید صریح وکیل نیاز دارد.")
    if step == "search":
        query = str(updated.get("query") or "").strip()
        if query:
            updated.setdefault("results", {})["search"] = search_case_documents(documents, query)
        else:
            updated.setdefault("results", {})["search"] = []
        next_step = "extract_compare"
    elif step == "extract_compare":
        updated.setdefault("results", {})["document_analysis"] = analyze_case_documents(documents)
        next_step = "lawyer_review"
    elif step == "lawyer_review":
        # Explicit human checkpoint; the agent cannot approve its own findings.
        updated.setdefault("results", {})["review_notice"] = (
            "یافته‌ها و تفاوت‌ها نامزد بررسی هستند؛ تطبیق با اصل اسناد بر عهده وکیل است."
        )
        next_step = "complete"
    elif step == "complete":
        updated["status"] = "COMPLETED"
        updated["completed_steps"] = list(updated.get("completed_steps") or []) + [step]
        return updated
    else:
        raise ValueError("مرحله گردش کار معتبر نیست.")
    updated["completed_steps"] = list(updated.get("completed_steps") or []) + [step]
    updated["current_step"] = next_step
    updated["status"] = "PENDING_APPROVAL"
    updated.setdefault("approvals", {}).pop(next_step, None)
    return updated


def workflow_summary(state: dict[str, Any]) -> dict[str, Any]:
    """Return a compact UI-safe summary without inventing legal conclusions."""
    state = state or {}
    results = state.get("results") or {}
    analysis = results.get("document_analysis") or {}
    return {
        "case_id": state.get("case_id"),
        "status": state.get("status"),
        "current_step": state.get("current_step"),
        "completed_steps": list(state.get("completed_steps") or []),
        "search_result_count": len(results.get("search") or []),
        "documents_analyzed": int(analysis.get("documents_analyzed") or 0),
        "comparison_candidate_count": int(analysis.get("comparison_candidate_count") or 0),
        "requires_lawyer_review": True,
    }
