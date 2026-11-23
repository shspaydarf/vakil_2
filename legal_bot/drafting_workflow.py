"""Unified user-facing workflow for case-based legal drafting.

V149-V160 remain separate internal engines. This module only orchestrates them
for Telegram UX: one start/resume action, minimal interruptions, and explicit
human-review stops. It does not add legal reasoning or external AI calls.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

from .brief_information import resolve_case_information
from .brief_planner import build_brief_plan
from .consistency_gate import build_case_consistency_gate
from .output_engine import build_case_output
from .db import get_case, get_case_text, get_drafting_workflow_session, save_drafting_workflow_session, init_drafting_workflow_tables
from .drafting_artifacts import save_draft_artifact

VERSION = 164


def _clean(value: Any) -> str:
    return str(value or "").strip()



def load_workflow_state(uid: int, cid: int) -> Dict[str, Any]:
    """Load the durable V163 checkpoint. The database is the source of truth."""
    init_drafting_workflow_tables()
    session = get_drafting_workflow_session(uid, int(cid))
    if not session:
        return {"case_id": int(cid), "status": "NOT_STARTED", "answers": {}, "deferred": []}
    state = dict(session.get("state") or {})
    state.setdefault("case_id", int(cid))
    state.setdefault("status", session.get("status") or "NOT_STARTED")
    state.setdefault("answers", {})
    state.setdefault("deferred", [])
    state["workflow_version"] = int(session.get("workflow_version") or VERSION)
    return state


def save_workflow_state(uid: int, cid: int, state: Dict[str, Any], status: str | None = None) -> Dict[str, Any]:
    """Persist a JSON-safe workflow checkpoint after each meaningful transition."""
    init_drafting_workflow_tables()
    payload = dict(state or {})
    payload["case_id"] = int(cid)
    if status is not None:
        payload["status"] = status
    payload.setdefault("status", "NOT_STARTED")
    payload["workflow_version"] = VERSION
    session = save_drafting_workflow_session(uid, int(cid), payload, payload["status"], VERSION)
    return dict(session.get("state") or payload)

def preflight_v150(uid: int, cid: int, brief_type: str = "لایحه دفاعیه", answers: Dict[str, Any] | None = None, deferred: set[str] | None = None) -> Dict[str, Any]:
    """Run V150 once as a lightweight gate before the expensive drafting chain."""
    case = get_case(uid, int(cid))
    if not case:
        return {"version": 150, "case_id": int(cid), "status": "CASE_NOT_FOUND", "questions": [], "items": []}
    if str(case.get("status") or "").lower() == "archived":
        return {"version": 150, "case_id": int(cid), "status": "CASE_ARCHIVED", "questions": [], "items": []}
    facts = _clean(get_case_text(uid, int(cid)))
    resolver = resolve_case_information(uid, int(cid), brief_type, facts, "", answers or {})
    required = [
        x for x in resolver.get("items", [])
        if x.get("importance") == "required" and x.get("status") in {"missing", "conflict"}
    ]
    resolver = deepcopy(resolver)
    deferred_set = {str(x) for x in (deferred or set())}
    resolver["deferred"] = sorted(deferred_set)
    resolver["workflow_required_missing"] = required
    resolver["workflow_ready"] = not required
    resolver["version"] = 150
    resolver["case_id"] = int(cid)
    return resolver


def next_required_question(preflight: Dict[str, Any], excluded_keys: set[str] | None = None) -> Dict[str, Any] | None:
    """Return the first actionable V150 question, honoring explicit deferrals."""
    excluded = {str(x) for x in (excluded_keys or set())}
    excluded.update(str(x) for x in (preflight.get("deferred") or []))
    for q in (preflight.get("questions") or []):
        if q.get("key") and str(q.get("key")) not in excluded:
            return dict(q)
    for item in (preflight.get("workflow_required_missing") or []):
        if item.get("key") and str(item.get("key")) not in excluded:
            return {
                "key": item.get("key"),
                "label": item.get("label") or item.get("key"),
                "question": item.get("question") or f"اطلاعات «{item.get('label') or item.get('key')}» را وارد کنید.",
            }
    return None


def workflow_question_text(preflight: Dict[str, Any]) -> str:
    q = next_required_question(preflight)
    if not q:
        return ""
    remaining = len(preflight.get("workflow_required_missing") or [])
    suffix = f"\n\nموارد ضروری باقی‌مانده: {remaining}" if remaining else ""
    return f"✏️ {q.get('question') or q.get('label')}" + suffix

def run_drafting_workflow(uid: int, cid: int, *, brief_type: str = "لایحه دفاعیه", answers: Dict[str, Any] | None = None, deferred: set[str] | None = None, allow_incomplete: bool = False) -> Dict[str, Any]:
    """Run the internal drafting pipeline as one user action.

    V150 is used as a preflight. If required information is missing/conflicting,
    execution stops before drafting. Otherwise V159 runs the existing V156->V157
    ->V158 chain and V160 presents the gated artifact.
    """
    cid = int(cid)
    case = get_case(uid, cid)
    if not case:
        return {"version": VERSION, "case_id": cid, "status": "CASE_NOT_FOUND", "plan": {}, "preflight": {}, "draft": None, "gate": None, "output": None, "artifact": None}
    if str(case.get("status") or "").lower() == "archived":
        return {"version": VERSION, "case_id": cid, "status": "CASE_ARCHIVED", "plan": {}, "preflight": {}, "draft": None, "gate": None, "output": None, "artifact": None}

    # Resume only this authenticated user's checkpoint for this case.
    prior = load_workflow_state(uid, cid)
    prior_type = str(prior.get("brief_type") or brief_type)
    same_brief_type = prior_type == str(brief_type)
    merged_answers = dict(prior.get("answers") or {}) if same_brief_type else {}
    if isinstance(answers, dict):
        merged_answers.update(answers)
    merged_deferred = set(str(x) for x in (prior.get("deferred") or [])) if same_brief_type else set()
    merged_deferred.update(str(x) for x in (deferred or set()))
    # Bound the checkpoint payload and accept only keys that the resolver has
    # actually asked about or exposes as a known information item.
    facts = _clean(get_case_text(uid, cid))
    base_preflight = preflight_v150(uid, cid, brief_type, {}, merged_deferred)
    known_keys = {str(x.get("key")) for x in (base_preflight.get("items") or []) if x.get("key")}
    known_keys.update(str(x.get("key")) for x in (base_preflight.get("questions") or []) if x.get("key"))
    labels = {str(x.get("key")): str(x.get("label") or x.get("key")) for x in (base_preflight.get("items") or [])}
    labels.update({str(x.get("key")): str(x.get("label") or x.get("key")) for x in (base_preflight.get("questions") or [])})
    safe_answers = {}
    for key, value in merged_answers.items():
        key = str(key)[:120]
        if key not in known_keys:
            continue
        if not isinstance(value, str):
            continue
        value = _clean(value)
        if value and len(value) <= 3000 and len(safe_answers) < 12:
            safe_answers[key] = value
    merged_answers = safe_answers
    preflight = preflight_v150(uid, cid, brief_type, merged_answers, merged_deferred)
    labels.update({str(x.get("key")): str(x.get("label") or x.get("key")) for x in (preflight.get("items") or [])})
    plan = build_brief_plan(facts=facts, brief_type=brief_type, case_text=facts, template_key="")
    if preflight.get("status") in {"CASE_NOT_FOUND", "CASE_ARCHIVED"}:
        return {
            "version": VERSION,
            "case_id": cid,
            "status": preflight.get("status"),
            "plan": plan,
            "preflight": preflight,
            "draft": None,
            "gate": None,
            "output": None,
            "artifact": None,
        }
    if not preflight.get("workflow_ready") and not allow_incomplete:
        save_workflow_state(uid, cid, {"answers": merged_answers, "deferred": sorted(merged_deferred), "preflight": preflight, "brief_type": brief_type}, "WAITING_FOR_INPUT")
        return {
            "version": VERSION,
            "case_id": cid,
            "status": "NEEDS_INFORMATION",
            "plan": plan,
            "preflight": preflight,
            "draft": None,
            "gate": None,
            "output": None,
            "artifact": None,
            "answers": merged_answers,
        }

    gate = build_case_consistency_gate(uid, cid, brief_type=brief_type, confirmed_answers=merged_answers, confirmed_answer_labels=labels)
    output = build_case_output(gate)
    status = "READY_FOR_REVIEW" if str(gate.get("status")) == "PASS" else "NEEDS_LAWYER_REVIEW"
    draft_text = str(output.get("draft_text") or "").strip()
    artifact = None
    if draft_text:
        # DRAFT-01: persist the actual user-facing artifact independently of
        # Telegram state. Each successful run creates an immutable version.
        artifact = save_draft_artifact(
            uid, cid, status=status, draft_text=draft_text,
            gate=gate, output=output, brief_type=brief_type
        )
        output = dict(output)
        output["artifact_id"] = artifact.get("id")
        output["artifact_version"] = artifact.get("version_no")
    save_workflow_state(uid, cid, {"answers": merged_answers, "deferred": sorted(merged_deferred), "preflight": preflight, "brief_type": brief_type, "artifact_id": (artifact or {}).get("id")}, status)
    return {
        "version": VERSION,
        "case_id": cid,
        "status": status,
        "plan": plan,
        "preflight": preflight,
        "draft": (gate.get("updated_draft") or gate.get("draft")),
        "gate": gate,
        "output": output,
        "artifact": artifact,
        "confirmed_answers": merged_answers,
        "confirmed_answer_labels": labels,
    }


def workflow_label(result: Dict[str, Any]) -> str:
    status = result.get("status")
    if status == "NEEDS_INFORMATION":
        return "⚠️ چند مورد از اطلاعات ضروری پرونده ناقص یا متعارض است."
    if status == "READY_FOR_REVIEW":
        return "✅ پیش‌نویس آماده بازبینی شماست."
    if status == "NEEDS_LAWYER_REVIEW":
        return "⚠️ پیش‌نویس ساخته شد، اما کنترل نهایی نیازمند بررسی وکیل است."
    if status == "CASE_NOT_FOUND":
        return "❌ پرونده پیدا نشد."
    return "📝 فرآیند لایحه‌نویسی آماده ادامه است."
