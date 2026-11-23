import pytest
from legal_bot.case_workflow_agent import (
    create_case_workflow, approve_step, run_approved_step, workflow_summary,
)

DOCS = [
    {"id": 1, "file_name": "قرارداد.txt", "extracted_text": "مبلغ قرارداد ۱۰۰۰ ریال\n[صفحه ۱]\nتاریخ ۱۴۰۲/۰۱/۰۱"},
    {"id": 2, "file_name": "الحاقیه.txt", "extracted_text": "مبلغ قرارداد ۲۰۰۰ ریال\n[صفحه ۲]\nتاریخ ۱۴۰۲/۰۲/۰۱"},
]


def test_workflow_requires_approval_before_running():
    state = create_case_workflow(7, "قرارداد")
    with pytest.raises(PermissionError):
        run_approved_step(state, DOCS)


def test_workflow_runs_search_then_waits_for_next_approval():
    state = approve_step(create_case_workflow(7, "قرارداد"), "search", approved=True)
    state = run_approved_step(state, DOCS)
    assert state["current_step"] == "extract_compare"
    assert state["status"] == "PENDING_APPROVAL"
    assert isinstance(state["results"]["search"], list)


def test_extract_compare_preserves_document_provenance():
    state = create_case_workflow(7)
    state["current_step"] = "extract_compare"
    state["status"] = "APPROVED_TO_RUN"
    state["approvals"] = {"extract_compare": True}
    state = run_approved_step(state, DOCS)
    analysis = state["results"]["document_analysis"]
    assert analysis["documents_analyzed"] == 2
    assert analysis["comparison_candidate_count"] >= 1
    assert all(f.get("document_id") for f in analysis["facts"])


def test_declined_step_pauses_workflow():
    state = approve_step(create_case_workflow(7), "search", approved=False)
    assert state["status"] == "PAUSED_BY_LAWYER"
    with pytest.raises(PermissionError):
        run_approved_step(state, DOCS)


def test_summary_always_requires_lawyer_review():
    summary = workflow_summary(create_case_workflow(7))
    assert summary["requires_lawyer_review"] is True
    assert summary["case_id"] == 7


def test_workflow_requires_approval_for_every_step_until_complete():
    state = create_case_workflow(7, "قرارداد")
    for expected in ("search", "extract_compare", "lawyer_review", "complete"):
        assert state["current_step"] == expected
        with pytest.raises(PermissionError):
            run_approved_step(state, DOCS)
        state = approve_step(state, expected, approved=True)
        state = run_approved_step(state, DOCS)
    assert state["status"] == "COMPLETED"
    assert state["completed_steps"] == ["search", "extract_compare", "lawyer_review", "complete"]

def test_workflow_decline_can_only_be_resumed_by_explicit_approval():
    state = approve_step(create_case_workflow(7), "search", approved=False)
    assert state["status"] == "PAUSED_BY_LAWYER"
    state = approve_step(state, "search", approved=True)
    assert state["status"] == "APPROVED_TO_RUN"
    state = run_approved_step(state, DOCS)
    assert state["current_step"] == "extract_compare"
