# -*- coding: utf-8 -*-
"""V158 — controlled, traceable self-critique and rewrite of V156/V157.

Local-first only. V158 never invents facts, authorities, citations, requests or
legal conclusions. It applies only deterministic, finding-scoped patches.
"""
from __future__ import annotations

from .text_utils import clean_whitespace as _clean

from copy import deepcopy
import re
from typing import Any, Dict, List, Optional, Tuple

from .adversarial_review import build_case_adversarial_review
from .brief_writer import render_structured_brief

VERSION = 158

SAFE_REWRITE_CATEGORIES = {
    "AMBIGUOUS_LANGUAGE",
    "UNSUPPORTED_CONCLUSION",
    "EVIDENCE_GAP",
    "CITATION_GAP",
    "COUNTERARGUMENT_MISSING",
    "LOGICAL_GAP",
    "PROCEDURAL_GAP",
}
BLOCKED_CATEGORIES = {
    "FACT_UNSUPPORTED",
    "FACT_CONTRADICTION",
    "AUTHORITY_GAP",
    "AUTHORITY_MISMATCH",
    "TEMPORAL_AUTHORITY_RISK",
    "CITATION_MISMATCH",
    "ISSUE_MISSING",
    "REQUEST_MISMATCH",
    "INTERNAL_INCONSISTENCY",
}

_RISKY = re.compile(r"قطعا|قطعاً|حتما|حتماً|بدیهی است|مسلماً|بدون تردید|محکوم خواهد شد|حتماً پیروز")




def _change(changes: List[Dict[str, Any]], finding: Dict[str, Any], target: str,
            before: Any, after: Any, change_type: str, refs=None,
            preserves_fact=True, preserves_citation=True) -> None:
    changes.append({
        "change_id": f"ch-{len(changes)+1:04d}",
        "finding_id": finding.get("finding_id"),
        "location": finding.get("location") or "draft",
        "target_path": target,
        "before": before,
        "after": after,
        "change_type": change_type,
        "reason": _clean(finding.get("problem") or finding.get("suggested_action")),
        "source_refs": list(refs or finding.get("source_refs") or []),
        "preserves_fact": bool(preserves_fact),
        "preserves_citation": bool(preserves_citation),
        "requires_lawyer_review": True,
    })


def _locate_argument(draft: Dict[str, Any], location: str) -> Optional[Tuple[int, Dict[str, Any]]]:
    for i, arg in enumerate(draft.get("arguments") or []):
        if str(arg.get("argument_id")) == str(location) or str(arg.get("issue_id")) == str(location):
            return i, arg
    return None


def _find_reasoning_step(arg: Dict[str, Any], finding_text: str = "") -> Optional[int]:
    """Resolve a rewrite target only when the finding identifies it exactly.

    V158 must never guess a reasoning step. Ambiguous locations are blocked.
    """
    steps = arg.get("reasoning_steps") or []
    ft = _clean(finding_text)
    if not ft:
        return None
    for i, step in enumerate(steps):
        if _clean(step.get("text")) == ft:
            return i
    return None


def _soften(text: str) -> str:
    """Deterministic language softening; never adds a new factual/legal proposition."""
    out = text
    replacements = [
        ("محکوم خواهد شد", "نیازمند بررسی و احراز شرایط مربوط است"),
        ("حتماً پیروز", "قابل بررسی در پرتو مستندات پرونده"),
        ("بدون تردید", "در صورت احراز مستندات مربوط"),
        ("بدیهی است", "قابل بررسی است"),
        ("مسلماً", "در صورت احراز شرایط مربوط"),
        ("قطعاً", "به‌طور قطعی قابل اعلام نیست"),
        ("قطعا", "به‌طور قطعی قابل اعلام نیست"),
        ("حتماً", "در صورت احراز شرایط مربوط"),
        ("حتما", "در صورت احراز شرایط مربوط"),
    ]
    for old, new in replacements:
        out = out.replace(old, new)
    return out


def _add_placeholder(arg: Dict[str, Any], text: str, *, kind: str) -> Tuple[str, Any, Any, bool]:
    """Append an auditable placeholder and return before/after snapshots + changed flag."""
    if kind == "evidence":
        field = "missing_support"
        arr = arg.setdefault(field, [])
        before = deepcopy(arr)
        marker = f"[V158 — نیازمند تکمیل مدرک: {_clean(text) or 'پشتوانه ادعا'}]"
        if not any(_clean(x.get("text")) == marker for x in arr if isinstance(x, dict)):
            arr.append({"type": "evidence", "text": marker, "requires_lawyer_review": True})
        return field, before, deepcopy(arr), arr != before
    if kind == "citation":
        field = "missing_support"
        arr = arg.setdefault(field, [])
        before = deepcopy(arr)
        marker = f"[V158 — نیازمند تکمیل citation موجود؛ منبع جدید ایجاد نشد: {_clean(text) or 'استناد'}]"
        if not any(_clean(x.get("text")) == marker for x in arr if isinstance(x, dict)):
            arr.append({"type": "citation", "text": marker, "requires_lawyer_review": True})
        return field, before, deepcopy(arr), arr != before
    if kind == "counterargument":
        field = "counterargument_placeholders"
        arr = arg.setdefault(field, [])
        before = deepcopy(arr)
        marker = f"[V158 — بررسی پاسخ به سیگنال مخالف: {_clean(text) or 'counterargument'}]"
        if marker not in arr:
            arr.append(marker)
        gaps = arg.setdefault("missing_support", [])
        gap = {"type": "counterargument", "text": marker, "requires_lawyer_review": True}
        if not any(_clean(x.get("text")) == marker for x in gaps if isinstance(x, dict)):
            gaps.append(gap)
        after = deepcopy(arr)
        return field, before, after, arr != before
    field = "review_placeholders"
    arr = arg.setdefault(field, [])
    before = deepcopy(arr)
    marker = f"[V158 — نیازمند بازبینی: {_clean(text) or 'بررسی ساختار استدلال'}]"
    if marker not in arr:
        arr.append(marker)
    return field, before, deepcopy(arr), arr != before


def _apply_finding(draft: Dict[str, Any], finding: Dict[str, Any], changes: List[Dict[str, Any]], blocked: List[Dict[str, Any]]) -> None:
    category = str(finding.get("category") or "")
    location = str(finding.get("location") or "draft")

    if category in BLOCKED_CATEGORIES:
        blocked.append({
            "finding_id": finding.get("finding_id"),
            "category": category,
            "location": location,
            "reason": "این نوع یافته نیازمند بررسی منبع/پرونده یا تصمیم وکیل است و V158 مجاز به اصلاح محتوایی خودکار آن نیست.",
            "requires_lawyer_review": True,
        })
        draft.setdefault("review_flags", []).append({"finding_id": finding.get("finding_id"), "category": category, "status": "blocked"})
        return

    if category == "AMBIGUOUS_LANGUAGE" or category == "UNSUPPORTED_CONCLUSION":
        hit = _locate_argument(draft, location)
        if not hit:
            blocked.append({"finding_id": finding.get("finding_id"), "category": category, "location": location, "reason": "محل استدلال در Draft پیدا نشد.", "requires_lawyer_review": True})
            return
        ai, arg = hit
        si = _find_reasoning_step(arg, finding.get("text"))
        if si is None:
            blocked.append({"finding_id": finding.get("finding_id"), "category": category, "location": location, "reason": "گام reasoning قابل اصلاح پیدا نشد.", "requires_lawyer_review": True})
            return
        step = arg["reasoning_steps"][si]
        before = step.get("text", "")
        after = _soften(before)
        if after == before:
            blocked.append({"finding_id": finding.get("finding_id"), "category": category, "location": location, "reason": "الگوی زبانی کنترل‌شده‌ای برای اصلاح پیدا نشد.", "requires_lawyer_review": True})
            return
        step["text"] = after
        _change(changes, finding, f"arguments[{ai}].reasoning_steps[{si}].text", before, after,
                "REMOVE_UNSUPPORTED_CONCLUSION" if category == "UNSUPPORTED_CONCLUSION" else "CLARIFY_LANGUAGE",
                preserves_fact=True, preserves_citation=True)
        return

    if category in {"EVIDENCE_GAP", "CITATION_GAP", "COUNTERARGUMENT_MISSING", "LOGICAL_GAP", "PROCEDURAL_GAP"}:
        hit = _locate_argument(draft, location)
        if not hit and category in {"PROCEDURAL_GAP"}:
            # Requested-relief gap is deliberately not auto-completed.
            blocked.append({"finding_id": finding.get("finding_id"), "category": category, "location": location, "reason": "خواسته/مسئله رویه‌ای از منبع پرونده باید تکمیل شود؛ V158 چیزی اختراع نمی‌کند.", "requires_lawyer_review": True})
            return
        if not hit:
            blocked.append({"finding_id": finding.get("finding_id"), "category": category, "location": location, "reason": "محل استدلال در Draft پیدا نشد.", "requires_lawyer_review": True})
            return
        ai, arg = hit
        kind = {"EVIDENCE_GAP": "evidence", "CITATION_GAP": "citation", "COUNTERARGUMENT_MISSING": "counterargument"}.get(category, "logic")
        field, before, after, changed = _add_placeholder(arg, finding.get("text") or finding.get("problem"), kind=kind)
        if not changed:
            blocked.append({"finding_id": finding.get("finding_id"), "category": category, "location": location,
                            "reason": "Placeholder از قبل وجود داشت؛ تغییر جدیدی اعمال نشد.", "status": "NOOP",
                            "requires_lawyer_review": True})
            return
        _change(changes, finding, f"arguments[{ai}].{field}", before, after,
                {"EVIDENCE_GAP": "ADD_MISSING_SUPPORT_PLACEHOLDER", "CITATION_GAP": "ADD_CITATION_REVIEW_PLACEHOLDER",
                 "COUNTERARGUMENT_MISSING": "ADD_COUNTERARGUMENT_PLACEHOLDER"}.get(category, "ADD_REVIEW_PLACEHOLDER"),
                preserves_fact=True, preserves_citation=True)
        return

    blocked.append({"finding_id": finding.get("finding_id"), "category": category, "location": location, "reason": "دسته یافته در سیاست V158 مجاز به اصلاح خودکار نیست.", "requires_lawyer_review": True})


def rewrite_structured_draft(draft: Dict[str, Any], review: Dict[str, Any]) -> Dict[str, Any]:
    """Apply only finding-scoped, deterministic changes to a deep copy of V156."""
    original = deepcopy(draft or {})
    revised = deepcopy(draft or {})
    changes: List[Dict[str, Any]] = []
    blocked: List[Dict[str, Any]] = []
    findings = list((review or {}).get("findings") or [])

    if not revised:
        return {
            "rewrite_id": "rw-empty",
            "base_draft_id": None,
            "source_review_version": 157,
            "changes": [], "updated_draft": {}, "unchanged_sections": [],
            "unresolved_findings": [f.get("finding_id") for f in findings],
            "blocked_rewrites": blocked,
            "warnings": ["Draft پایه خالی است؛ بازنویسی انجام نشد."],
            "requires_lawyer_review": True,
            "legal_conclusion_generated": False,
            "final_brief_generated": False,
        }

    # Process each V157 finding at most once; duplicate IDs must not cause duplicate patches.
    unique_findings = []
    seen_finding_ids = set()
    duplicate_ids = []
    for finding in findings:
        fid = str(finding.get("finding_id") or "")
        if fid and fid in seen_finding_ids:
            duplicate_ids.append(fid)
            continue
        if fid:
            seen_finding_ids.add(fid)
        unique_findings.append(finding)
    findings = unique_findings

    critiques = []
    for finding in findings:
        category = str(finding.get("category") or "")
        safe = category in SAFE_REWRITE_CATEGORIES
        scope = "finding-scoped deterministic patch" if safe else "blocked — source/fact/legal review required"
        critiques.append({
            "critique_id": f"crit-{len(critiques)+1:04d}",
            "finding_id": finding.get("finding_id"),
            "category": category,
            "location": finding.get("location") or "draft",
            "original_text": finding.get("text") or "",
            "problem": finding.get("problem") or "",
            "safe_to_rewrite": safe,
            "rewrite_scope": scope,
            "requires_lawyer_review": True,
        })
        _apply_finding(revised, finding, changes, blocked)

    # V158 invariants: never alter facts, authorities, citations or requested relief directly.
    for key in ("facts", "authorities", "citations", "requested_relief", "issues"):
        revised[key] = deepcopy(original.get(key, []))

    # Preserve trace and append V158 trace metadata; upstream trace itself remains immutable.
    revised["source_trace"] = deepcopy(original.get("source_trace") or {})
    revised["source_trace"]["v158_change_ids"] = [c["change_id"] for c in changes]
    revised["source_trace"]["v158_finding_ids"] = [f.get("finding_id") for f in findings]
    revised["source_trace"]["v158_blocked_finding_ids"] = [b.get("finding_id") for b in blocked]
    revised["review_status"] = "v158_rewrite_requires_lawyer_review"
    revised["requires_lawyer_review"] = True
    revised["legal_conclusion_generated"] = False
    revised["final_brief_generated"] = False
    revised["rendered_text"] = render_structured_brief(revised)

    unresolved = [f.get("finding_id") for f in findings if f.get("finding_id") not in {c.get("finding_id") for c in changes}]
    status = "NO_CHANGE_REQUIRED" if not findings else ("SAFE_REWRITES_APPLIED" if changes and not blocked else ("PARTIAL_REWRITE" if changes else "REWRITE_BLOCKED"))
    return {
        "rewrite_id": f"rw-{revised.get('case_id','x')}-158",
        "case_id": revised.get("case_id"),
        "base_draft_id": original.get("draft_id"),
        "source_review_version": 157,
        "status": status,
        "critiques": critiques,
        "original_draft": original,
        "changes": changes,
        "updated_draft": revised,
        "unchanged_sections": [k for k in ("facts", "issues", "authorities", "citations", "requested_relief") if original.get(k, []) == revised.get(k, [])],
        "unresolved_findings": unresolved,
        "blocked_rewrites": blocked,
        "warnings": ["V158 فقط اصلاحات محدود و ردیابی‌شده را اعمال کرده است.", "هیچ واقعیت، منبع قانونی، citation یا خواسته جدیدی ایجاد نشده است."] + ([f"Duplicate V157 finding IDs ignored: {sorted(set(duplicate_ids))}"] if duplicate_ids else []),
        "source_trace": deepcopy(revised.get("source_trace") or {}),
        "review_status": "lawyer_review_required",
        "requires_lawyer_review": True,
        "legal_conclusion_generated": False,
        "final_brief_generated": False,
        "api_used": False,
    }


def build_case_rewrite(uid: int, cid: int, *, brief_type: str = "لایحه دفاعیه", confirmed_answers=None, confirmed_answer_labels=None) -> Dict[str, Any]:
    """Run V157 once, then apply V158 controlled rewrite to its V156 draft."""
    review = build_case_adversarial_review(uid, cid, brief_type=brief_type, confirmed_answers=confirmed_answers, confirmed_answer_labels=confirmed_answer_labels)
    if review.get("error"):
        return {"version": VERSION, "case_id": int(cid), "error": review["error"], "api_used": False}
    result = rewrite_structured_draft(review.get("draft") or {}, review)
    result.update({
        "version": VERSION,
        "case_id": int(cid),
        "v157_findings": review.get("findings") or [],
        "v157_counts": review.get("counts") or {},
        "resolver_path": ["v156_structured_draft", "v157_adversarial_review", "v158_controlled_rewrite"],
    })
    return result


def render_rewrite(result: Dict[str, Any], limit: int = 18) -> str:
    r = result or {}
    if r.get("error"):
        return "❌ V158 اجرا نشد: " + _clean(r.get("error"))
    lines = ["🔧 V158 — بازنویسی کنترل‌شده", "",
             f"وضعیت: {r.get('status')}",
             f"اصلاحات اعمال‌شده: {len(r.get('changes') or [])}",
             f"موارد مسدود/نیازمند وکیل: {len(r.get('blocked_rewrites') or [])}",
             "", "هیچ واقعیت، منبع قانونی، citation یا خواسته جدیدی به‌صورت خودکار ایجاد نشده است."]
    for ch in (r.get("changes") or [])[:max(1, limit)]:
        lines += ["", f"✏️ {ch.get('change_id')} · {ch.get('change_type')}",
                  f"Finding: {ch.get('finding_id')}", f"مسیر: {ch.get('target_path')}",
                  f"قبل: {_clean(ch.get('before'))[:500]}", f"بعد: {_clean(ch.get('after'))[:500]}"]
    if r.get("blocked_rewrites"):
        lines += ["", "⛔ مواردی که عمداً خودکار اصلاح نشدند:"]
        for b in r["blocked_rewrites"][:max(1, limit)]:
            lines.append(f"• {b.get('finding_id')} · {b.get('category')} — {b.get('reason')}")
    lines += ["", "⚖️ خروجی همچنان نیازمند بررسی و تأیید وکیل است.", "🔒 V158 محلی است و API خارجی استفاده نکرده است."]
    return "\n".join(lines)
