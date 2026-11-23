# -*- coding: utf-8 -*-
"""V159 — Citation & Consistency Gate for the V158 revised legal draft.

Local-first, read-only gate. V159 never rewrites the draft and never invents
facts, authorities, citations, requests, issues, or legal conclusions.
"""
from __future__ import annotations

from .text_utils import clean_whitespace as _clean

from copy import deepcopy
import re
from typing import Any, Dict, Iterable, List, Tuple

from .brief_writer import render_structured_brief
from .rewrite_engine import build_case_rewrite

VERSION = 159


_ALLOWED_CHANGE_SCOPES = {
    "AMBIGUOUS_LANGUAGE": ("arguments[", "arguments."),
    "UNSUPPORTED_CONCLUSION": ("arguments[", "arguments."),
    "EVIDENCE_GAP": ("missing_support",),
    "CITATION_GAP": ("missing_support",),
    "COUNTERARGUMENT_MISSING": ("counterargument_placeholders", "missing_support"),
    "LOGICAL_GAP": ("review_placeholders",),
    "PROCEDURAL_GAP": ("review_placeholders",),
}

_ALLOWED_CHANGE_TYPES = {
    "AMBIGUOUS_LANGUAGE": {"CLARIFY_LANGUAGE"},
    "UNSUPPORTED_CONCLUSION": {"REMOVE_UNSUPPORTED_CONCLUSION"},
    "EVIDENCE_GAP": {"ADD_MISSING_SUPPORT_PLACEHOLDER"},
    "CITATION_GAP": {"ADD_CITATION_REVIEW_PLACEHOLDER"},
    "COUNTERARGUMENT_MISSING": {"ADD_COUNTERARGUMENT_PLACEHOLDER"},
    "LOGICAL_GAP": {"ADD_REVIEW_PLACEHOLDER"},
    "PROCEDURAL_GAP": {"ADD_REVIEW_PLACEHOLDER"},
}

_IMMUTABLE_ARGUMENT_KEYS = (
    "argument_id", "issue_id", "heading", "position", "claims",
    "supporting_evidence", "authority_refs", "counterargument_refs", "unsupported_parts",
)

REQUIRED_TRACE_KEYS = (
    "v149_plan",
    "v151_event_ids",
    "v152_issue_ids",
    "v153_claim_ids",
    "v154_authority_ids",
    "v155_strategy_issue_ids",
    "argument_ids",
)

RISKY_CONCLUSION = re.compile(
    r"محکوم خواهد شد|حتماً پیروز|قطعا|قطعاً|حتما|حتماً|بدیهی است|مسلماً|بدون تردید|نتیجه قطعی"
)




def _ids(items: Iterable[Dict[str, Any]], key: str) -> List[str]:
    return [str(x.get(key)) for x in items or [] if x.get(key) is not None]


def _add(findings: List[Dict[str, Any]], category: str, severity: str,
         location: str, problem: str, why: str, source_refs=None,
         suggested_action: str = "بررسی دستی توسط وکیل") -> None:
    findings.append({
        "finding_id": f"gate-{len(findings)+1:04d}",
        "category": category,
        "severity": severity,
        "location": location,
        "text": "",
        "problem": problem,
        "why_it_matters": why,
        "source_refs": list(source_refs or []),
        "suggested_action": suggested_action,
        "requires_lawyer_review": True,
    })


def _immutable_integrity(base: Dict[str, Any], revised: Dict[str, Any], findings: List[Dict[str, Any]]) -> None:
    for key, category in (
        ("facts", "FACT_CHANGED"),
        ("authorities", "AUTHORITY_CHANGED"),
        ("citations", "CITATION_CHANGED"),
        ("requested_relief", "REQUEST_CHANGED"),
        ("issues", "ISSUE_CHANGED"),
    ):
        if base.get(key, []) != revised.get(key, []):
            _add(findings, category, "high", key,
                 f"بخش {key} بین Draft پایه V156 و خروجی V158 تغییر کرده است.",
                 "V158 نباید این بخش را بدون trace اختصاصی تغییر دهد.",
                 suggested_action="تغییر را متوقف و مسیر منبع/تصمیم وکیل را بررسی کنید.")


def _claim_integrity(base: Dict[str, Any], revised: Dict[str, Any], findings: List[Dict[str, Any]]) -> None:
    b = sorted(str(c) for a in base.get("arguments", []) for c in a.get("claims", []) if c is not None)
    r = sorted(str(c) for a in revised.get("arguments", []) for c in a.get("claims", []) if c is not None)
    if b != r:
        _add(findings, "CLAIM_TRACE_BROKEN", "high", "arguments.claims",
             "مجموعه claim_idهای متصل به استدلال پس از V158 تغییر کرده است.",
             "ممکن است اتصال ادعا به Evidence/Authority قطع شده باشد.",
             sorted(set(b) ^ set(r)))


def _evidence_integrity(base: Dict[str, Any], revised: Dict[str, Any], findings: List[Dict[str, Any]]) -> None:
    def evidence_signature(draft: Dict[str, Any]) -> List[Tuple[str, str, str, str, str]]:
        out = []
        for arg in draft.get("arguments", []):
            aid = str(arg.get("argument_id"))
            for item in arg.get("supporting_evidence", []) or []:
                cid = str(item.get("claim_id"))
                for e in item.get("evidence", []) or []:
                    out.append((aid, cid, str(e.get("document_id")), str(e.get("char_start")), str(e.get("char_end"))))
        return sorted(out)
    if evidence_signature(base) != evidence_signature(revised):
        _add(findings, "EVIDENCE_TRACE_BROKEN", "high", "arguments.supporting_evidence",
             "اتصال Evidence بین V156 و V158 تغییر کرده است.",
             "مدرک ممکن است حذف، جابه‌جا یا به Claim دیگری متصل شده باشد.",
             suggested_action="Evidence را با V153 تطبیق دهید و از هر تغییر خودکار جلوگیری کنید.")

    # Explicit claim isolation check: an evidence row may only sit under its
    # own claim_id in the structured argument payload.
    for arg in revised.get("arguments", []) or []:
        for item in arg.get("supporting_evidence", []) or []:
            cid = item.get("claim_id")
            for e in item.get("evidence", []) or []:
                if e.get("claim_id") is not None and str(e.get("claim_id")) != str(cid):
                    _add(findings, "EVIDENCE_CLAIM_MISMATCH", "high",
                         str(arg.get("argument_id")),
                         "Evidence با claim_id متفاوت در زیر یک Claim ثبت شده است.",
                         "این الگو می‌تواند باعث نشت Evidence بین ادعاهای پرونده شود.",
                         [cid, e.get("claim_id")])


def _authority_integrity(base: Dict[str, Any], revised: Dict[str, Any], findings: List[Dict[str, Any]]) -> None:
    def refs(draft: Dict[str, Any]) -> List[Tuple[str, str, str, str, str]]:
        out = []
        for arg in draft.get("arguments", []) or []:
            for ref in arg.get("authority_refs", []) or []:
                out.append((str(arg.get("argument_id")), str(ref.get("authority_id")),
                            str(ref.get("claim_id")), str(ref.get("verification_status")),
                            str(ref.get("temporal_status"))))
        return sorted(out)
    if refs(base) != refs(revised):
        _add(findings, "AUTHORITY_TRACE_BROKEN", "high", "arguments.authority_refs",
             "اتصال Authority بین V156 و V158 تغییر کرده است.",
             "ممکن است منبع قانونی از Claim/Issue اصلی جدا شده یا منبع دیگری جایگزین شده باشد.")

    authority_ids = set(_ids(revised.get("authorities", []), "authority_id"))
    for arg in revised.get("arguments", []) or []:
        for ref in arg.get("authority_refs", []) or []:
            aid = str(ref.get("authority_id"))
            if aid not in authority_ids:
                _add(findings, "AUTHORITY_REFERENCE_ORPHAN", "high", str(arg.get("argument_id")),
                     "Authority reference در Draft به Authority موجود متصل نیست.",
                     "Citation قابل راستی‌آزمایی نخواهد بود.", [aid])


def _citation_integrity(draft: Dict[str, Any], findings: List[Dict[str, Any]]) -> None:
    authority_ids = set(_ids(draft.get("authorities", []), "authority_id"))
    claim_ids = set(_ids([{"claim_id": c} for a in draft.get("arguments", []) for c in a.get("claims", [])], "claim_id"))
    ref_keys = {
        (str(ref.get("authority_id")), str(ref.get("claim_id")), str(arg.get("issue_id")))
        for arg in draft.get("arguments", []) or []
        for ref in arg.get("authority_refs", []) or []
    }
    for citation in draft.get("citations", []) or []:
        aid = str(citation.get("authority_id"))
        if aid not in authority_ids:
            _add(findings, "CITATION_ORPHAN", "high", str(citation.get("citation_id")),
                 "Citation به Authority موجود در Draft متصل نیست.",
                 "استناد بدون منبع قابل ردیابی نباید از Gate عبور کند.", [aid])
        cid = citation.get("claim_id")
        if cid is not None and str(cid) not in claim_ids:
            _add(findings, "CITATION_CLAIM_ORPHAN", "high", str(citation.get("citation_id")),
                 "Citation دارای claim_id است اما Claim مربوط در arguments یافت نشد.",
                 "مسیر Claim → Citation شکسته است.", [cid])
        ref_key = (str(citation.get("authority_id")), str(citation.get("claim_id")), str(citation.get("issue_id")))
        if ref_key not in ref_keys:
            _add(findings, "CITATION_REFERENCE_MISMATCH", "high", str(citation.get("citation_id")),
                 "Citation در هیچ authority_ref متناظر در arguments دیده نمی‌شود.",
                 "ممکن است Citation از مسیر استدلال جدا شده یا به Claim/Issue دیگری تعلق داشته باشد.",
                 [citation.get("authority_id"), citation.get("claim_id"), citation.get("issue_id")])
        if citation.get("verification_status") != "verified":
            _add(findings, "CITATION_UNVERIFIED", "medium", str(citation.get("citation_id")),
                 "Citation وضعیت verified ندارد.",
                 "این منبع نباید به‌عنوان پشتوانه نهایی تلقی شود.", [aid],
                 "وضعیت Verification را در V154 بررسی کنید.")
        temporal = citation.get("temporal_status")
        if temporal not in {"pre_or_same_event_date", "unknown", "bounded_but_case_date_unknown", None}:
            _add(findings, "CITATION_TEMPORAL_RISK", "high", str(citation.get("citation_id")),
                 "وضعیت زمانی Citation برای پرونده مناسب/تأییدشده نیست.",
                 "ممکن است منبع در زمان مرتبط با پرونده قابل اعمال نباشد.", [aid],
                 "وضعیت زمانی V154 و تاریخ‌های پرونده را بررسی کنید.")


def _trace_integrity(base: Dict[str, Any], revised: Dict[str, Any], findings: List[Dict[str, Any]]) -> None:
    b = base.get("source_trace") or {}
    r = revised.get("source_trace") or {}
    missing = [k for k in REQUIRED_TRACE_KEYS if k not in r]
    if missing:
        _add(findings, "SOURCE_TRACE_MISSING", "high", "source_trace",
             "شناسه‌های upstream در source_trace خروجی V158 ناقص هستند.",
             "منشأ Facts/Issues/Claims/Authorities/Strategies قابل ردیابی نخواهد بود.", missing)
    for key in REQUIRED_TRACE_KEYS:
        if key in b and r.get(key) != b.get(key):
            _add(findings, "SOURCE_TRACE_CHANGED", "high", f"source_trace.{key}",
                 f"فیلد {key} نسبت به V156 تغییر کرده است.",
                 "V158 باید trace upstream را immutable نگه دارد.", [key])

    argument_claims = {str(c) for a in revised.get("arguments", []) or [] for c in a.get("claims", []) if c is not None}
    traced_claims = {str(c) for c in r.get("v153_claim_ids", []) or [] if c is not None}
    if not argument_claims.issubset(traced_claims):
        _add(findings, "CLAIM_OUTSIDE_SOURCE_TRACE", "high", "source_trace.v153_claim_ids",
             "حداقل یک Claim مورد استفاده در arguments در source_trace V153 وجود ندارد.",
             "مسیر Claim → V153 قابل بازسازی نیست.", sorted(argument_claims - traced_claims))

    argument_authorities = {str(ref.get("authority_id")) for a in revised.get("arguments", []) or [] for ref in a.get("authority_refs", []) if ref.get("authority_id")}
    traced_authorities = {str(a) for a in r.get("v154_authority_ids", []) or [] if a is not None}
    if not argument_authorities.issubset(traced_authorities):
        _add(findings, "AUTHORITY_OUTSIDE_SOURCE_TRACE", "high", "source_trace.v154_authority_ids",
             "حداقل یک Authority مورد استفاده در arguments در source_trace V154 وجود ندارد.",
             "مسیر Authority → V154 قابل بازسازی نیست.", sorted(argument_authorities - traced_authorities))

    for key in ("v158_change_ids", "v158_finding_ids", "v158_blocked_finding_ids"):
        if key not in r:
            _add(findings, "V158_TRACE_MISSING", "medium", f"source_trace.{key}",
                 f"متادیتای {key} در خروجی V158 موجود نیست.",
                 "ارتباط Gate با اصلاحات V158 ضعیف می‌شود.", [key])


def _coverage(base: Dict[str, Any], revised: Dict[str, Any], findings: List[Dict[str, Any]]) -> None:
    for key, category in (("issues", "ISSUE_COVERAGE_BROKEN"),):
        b = set(_ids(base.get(key, []), "issue_id"))
        r = set(_ids(revised.get(key, []), "issue_id"))
        if b != r:
            _add(findings, category, "high", key,
                 "مجموعه مسائل حقوقی بین V156 و V158 تغییر کرده است.",
                 "ممکن است بخشی از دامنه تحلیل حذف یا تغییر کرده باشد.", sorted(b ^ r))

    b_args = {str(a.get("issue_id")) for a in base.get("arguments", []) if a.get("issue_id")}
    r_args = {str(a.get("issue_id")) for a in revised.get("arguments", []) if a.get("issue_id")}
    if b_args != r_args:
        _add(findings, "STRATEGY_ARGUMENT_COVERAGE_BROKEN", "high", "arguments",
             "Issueهای دارای argument بین V156 و V158 تغییر کرده‌اند.",
             "ممکن است اتصال Strategy → Argument قطع شده باشد.", sorted(b_args ^ r_args))


def _argument_structure_integrity(base: Dict[str, Any], revised: Dict[str, Any], findings: List[Dict[str, Any]]) -> None:
    bmap = {str(a.get("argument_id")): a for a in base.get("arguments", []) or []}
    rmap = {str(a.get("argument_id")): a for a in revised.get("arguments", []) or []}
    if set(bmap) != set(rmap):
        _add(findings, "ARGUMENT_STRUCTURE_CHANGED", "high", "arguments",
             "مجموعه argument_idها بین V156 و V158 تغییر کرده است.",
             "V158 نباید argument جدید بسازد یا argument موجود را حذف کند.")
        return
    for aid in sorted(bmap):
        for key in _IMMUTABLE_ARGUMENT_KEYS:
            if bmap[aid].get(key, []) != rmap[aid].get(key, []):
                _add(findings, "ARGUMENT_STRUCTURE_CHANGED", "high", f"arguments[{aid}].{key}",
                     f"فیلد ساختاری {key} در argument تغییر کرده است.",
                     "فقط reasoning و placeholderهای مشخص‌شده در سیاست V158 مجاز به تغییر هستند.", [aid])


def _change_scope_integrity(v158_result: Dict[str, Any], findings: List[Dict[str, Any]]) -> None:
    findings_by_id = {str(f.get("finding_id")): f for f in v158_result.get("v157_findings", []) or [] if f.get("finding_id")}
    seen = set()
    for change in v158_result.get("changes") or []:
        fid = str(change.get("finding_id"))
        if fid in seen:
            _add(findings, "DUPLICATE_CHANGE_FOR_FINDING", "high", str(change.get("change_id")),
                 "برای یک Finding بیش از یک Change ثبت شده است.",
                 "هر Finding باید یک Patch کنترل‌شده و قابل ردیابی داشته باشد.", [fid])
        seen.add(fid)
        f = findings_by_id.get(fid)
        if not f:
            continue
        category = str(f.get("category") or "")
        path = str(change.get("target_path") or "")
        allowed = _ALLOWED_CHANGE_SCOPES.get(category, ())
        if allowed and not any(token in path for token in allowed):
            _add(findings, "CHANGE_SCOPE_VIOLATION", "high", path,
                 f"Change برای Finding نوع {category} خارج از محدوده مجاز ثبت شده است.",
                 "V158 باید فقط در Pathهای مجاز همان Finding تغییر ایجاد کند.", [fid])
        allowed_types = _ALLOWED_CHANGE_TYPES.get(category, set())
        if allowed_types and change.get("change_type") not in allowed_types:
            _add(findings, "CHANGE_TYPE_VIOLATION", "high", str(change.get("change_id")),
                 f"نوع Change {change.get('change_type')} برای Finding نوع {category} مجاز نیست.",
                 "Policy تغییر باید با نوع Finding منطبق باشد.", [fid])
        if change.get("before") == change.get("after"):
            _add(findings, "NOOP_CHANGE", "medium", str(change.get("change_id")),
                 "Change Log تغییری را ثبت کرده که before و after آن یکسان است.",
                 "Change Log باید فقط تغییرات واقعی را ثبت کند.", [fid])


def _blocked_trace_integrity(v158_result: Dict[str, Any], findings: List[Dict[str, Any]]) -> None:
    findings_by_id = {str(f.get("finding_id")): f for f in v158_result.get("v157_findings", []) or [] if f.get("finding_id")}
    blocked_ids = {str(x) for x in v158_result.get("source_trace", {}).get("v158_blocked_finding_ids", []) or []}
    blocked_objects = {str(x.get("finding_id")) for x in v158_result.get("blocked_rewrites", []) or [] if x.get("finding_id")}
    if blocked_ids != blocked_objects:
        _add(findings, "BLOCKED_TRACE_BROKEN", "high", "source_trace.v158_blocked_finding_ids",
             "شناسه‌های blocked در source_trace با blocked_rewrites یکسان نیستند.",
             "Gate نمی‌تواند مشخص کند کدام Finding عمداً برای بررسی وکیل متوقف شده است.")
    for fid in blocked_ids:
        if fid not in findings_by_id:
            _add(findings, "BLOCKED_FINDING_ORPHAN", "high", "source_trace.v158_blocked_finding_ids",
                 "یک blocked finding در V158 به Finding معتبر V157 متصل نیست.",
                 "ردیابی علت توقف بازنویسی شکسته است.", [fid])


def _duplicate_finding_ids(v158_result: Dict[str, Any], findings: List[Dict[str, Any]]) -> None:
    ids = [str(f.get("finding_id")) for f in v158_result.get("v157_findings", []) or [] if f.get("finding_id")]
    dupes = sorted({x for x in ids if ids.count(x) > 1})
    if dupes:
        _add(findings, "DUPLICATE_FINDING_ID", "medium", "v157_findings",
             "V157 بیش از یک بار یک finding_id یکسان ارسال کرده است.",
             "V158 باید فقط یک Patch برای هر Finding اعمال کند.", dupes,
             "منبع V157 را بررسی کنید؛ V158 باید Duplicateها را بدون تکرار Patch مدیریت کند.")

def _change_trace(v158_result: Dict[str, Any], findings: List[Dict[str, Any]]) -> None:
    v157_ids = {str(f.get("finding_id")) for f in v158_result.get("v157_findings", []) if f.get("finding_id")}
    changes = v158_result.get("changes") or []
    changed_findings = set()
    for change in changes:
        fid = str(change.get("finding_id"))
        changed_findings.add(fid)
        if fid not in v157_ids:
            _add(findings, "CHANGE_WITHOUT_FINDING", "high", str(change.get("change_id")),
                 "یک تغییر V158 بدون Finding معتبر V157 ثبت شده است.",
                 "هر اصلاح باید دامنه و علت قابل ردیابی داشته باشد.", [fid])
        if change.get("before") == change.get("after"):
            _add(findings, "NOOP_CHANGE", "medium", str(change.get("change_id")),
                 "Change Log تغییری را ثبت کرده که before و after آن یکسان است.",
                 "Change Log باید فقط تغییرات واقعی را ثبت کند.", [fid])
    for fid in v158_result.get("source_trace", {}).get("v158_change_ids", []) or []:
        if not any(str(c.get("change_id")) == str(fid) for c in changes):
            _add(findings, "CHANGE_TRACE_BROKEN", "high", "source_trace.v158_change_ids",
                 "شناسه change در source_trace به Change واقعی متصل نیست.",
                 "مسیر اصلاح V158 قابل بازسازی نیست.", [fid])


def _safety_flags(draft: Dict[str, Any], findings: List[Dict[str, Any]]) -> None:
    if draft.get("requires_lawyer_review") is not True:
        _add(findings, "LAWYER_REVIEW_FLAG_LOST", "high", "requires_lawyer_review",
             "خروجی V158 نیازمند بازبینی وکیل علامت‌گذاری نشده است.",
             "Gate نباید خروجی را به‌عنوان نسخه نهایی تلقی کند.")
    if draft.get("legal_conclusion_generated") is True:
        _add(findings, "LEGAL_CONCLUSION_FLAG", "high", "legal_conclusion_generated",
             "V158 خروجی را حاوی نتیجه حقوقی نهایی علامت‌گذاری کرده است.",
             "نتیجه حقوقی قطعی نباید به‌صورت خودکار تولید شود.")
    if draft.get("final_brief_generated") is True:
        _add(findings, "FINAL_BRIEF_FLAG", "high", "final_brief_generated",
             "V158 خروجی را نسخه نهایی لایحه علامت‌گذاری کرده است.",
             "نهایی‌سازی باید خارج از این زنجیره و با بررسی وکیل باشد.")


def _risky_new_language(base: Dict[str, Any], revised: Dict[str, Any], findings: List[Dict[str, Any]]) -> None:
    def risky(draft: Dict[str, Any]) -> List[str]:
        return [
            _clean(step.get("text"))
            for arg in draft.get("arguments", []) or []
            for step in arg.get("reasoning_steps", []) or []
            if RISKY_CONCLUSION.search(_clean(step.get("text")))
        ]
    before = risky(base)
    after = risky(revised)
    for text in after:
        if text not in before:
            _add(findings, "NEW_RISKY_CONCLUSION_LANGUAGE", "high", "arguments.reasoning_steps", text,
                 "V158 عبارتی نتیجه‌محور/قطعی اضافه کرده است.",
                 "عبارت را به مسیر بررسی مشروط برگردانید؛ V159 خودکار اصلاح نمی‌کند.")


def gate_v158_result(v158_result: Dict[str, Any]) -> Dict[str, Any]:
    """Audit an already-created V158 result without changing it."""
    result = v158_result or {}
    base = deepcopy(result.get("original_draft") or {})
    revised = deepcopy(result.get("updated_draft") or {})
    findings: List[Dict[str, Any]] = []

    if not base or not revised:
        _add(findings, "DRAFT_MISSING", "high", "draft",
             "Draft پایه یا Draft بازنویسی‌شده موجود نیست.",
             "هیچ Gate قابل اتکایی بدون هر دو snapshot ممکن نیست.")
    else:
        _immutable_integrity(base, revised, findings)
        _argument_structure_integrity(base, revised, findings)
        _claim_integrity(base, revised, findings)
        _evidence_integrity(base, revised, findings)
        _authority_integrity(base, revised, findings)
        _citation_integrity(revised, findings)
        _trace_integrity(base, revised, findings)
        _coverage(base, revised, findings)
        _risky_new_language(base, revised, findings)
        _safety_flags(revised, findings)

        rendered = render_structured_brief(revised)
        if rendered != revised.get("rendered_text"):
            _add(findings, "RENDER_MISMATCH", "high", "rendered_text",
                 "rendered_text با Structured Draft فعلی یکسان نیست.",
                 "ممکن است کاربر متنی متفاوت از Draft ممیزی‌شده ببیند.",
                 suggested_action="rendered_text را فقط از Structured Draft بازتولید کنید.")

    _change_trace(result, findings)
    _change_scope_integrity(result, findings)
    _blocked_trace_integrity(result, findings)
    _duplicate_finding_ids(result, findings)

    high = sum(1 for f in findings if f.get("severity") == "high")
    medium = sum(1 for f in findings if f.get("severity") == "medium")
    low = sum(1 for f in findings if f.get("severity") == "low")
    status = "PASS" if not findings else "BLOCKED"
    return {
        "version": VERSION,
        "case_id": result.get("case_id"),
        "base_draft_id": result.get("base_draft_id"),
        "rewrite_id": result.get("rewrite_id"),
        "status": status,
        "findings": findings,
        "counts": {"high": high, "medium": medium, "low": low},
        "checked": [
            "fact_integrity", "claim_integrity", "evidence_integrity",
            "authority_integrity", "citation_integrity", "issue_coverage",
            "strategy_argument_coverage", "requested_relief_integrity",
            "source_trace_integrity", "change_trace", "render_consistency",
            "safety_flags", "no_new_risky_conclusion_language",
        ],
        "draft_unchanged_by_gate": True,
        "updated_draft": revised,
        "changes": deepcopy(result.get("changes") or []),
        "blocked_rewrites": deepcopy(result.get("blocked_rewrites") or []),
        "v157_findings": deepcopy(result.get("v157_findings") or []),
        "source_trace": deepcopy(result.get("source_trace") or {}),
        "requires_lawyer_review": True,
        "legal_conclusion_generated": False,
        "final_brief_generated": False,
        "api_used": False,
    }


def build_case_consistency_gate(uid: int, cid: int, *, brief_type: str = "لایحه دفاعیه", confirmed_answers=None, confirmed_answer_labels=None) -> Dict[str, Any]:
    """Run V158 then V159 as a single deterministic local pipeline."""
    v158 = build_case_rewrite(uid, cid, brief_type=brief_type, confirmed_answers=confirmed_answers, confirmed_answer_labels=confirmed_answer_labels)
    if v158.get("error"):
        return {"version": VERSION, "case_id": int(cid), "status": "BLOCKED",
                "findings": [{"finding_id": "gate-error", "category": "V158_ERROR", "severity": "high",
                              "location": "v158", "text": "", "problem": _clean(v158.get("error")),
                              "why_it_matters": "V159 بدون Draft پایه قابل اجرا نیست.",
                              "source_refs": [], "suggested_action": "V158 را بررسی کنید.",
                              "requires_lawyer_review": True}],
                "counts": {"high": 1, "medium": 0, "low": 0},
                "requires_lawyer_review": True, "legal_conclusion_generated": False,
                "final_brief_generated": False, "api_used": False}
    gate = gate_v158_result(v158)
    gate["resolver_path"] = ["v156_structured_draft", "v157_adversarial_review", "v158_controlled_rewrite", "v159_consistency_gate"]
    gate["v158_status"] = v158.get("status")
    gate["v158_change_count"] = len(v158.get("changes") or [])
    gate["v158_blocked_count"] = len(v158.get("blocked_rewrites") or [])
    gate["v157_counts"] = v158.get("v157_counts") or {}
    return gate


def render_consistency_gate(result: Dict[str, Any], limit: int = 18) -> str:
    r = result or {}
    if r.get("error"):
        return "❌ V159 اجرا نشد: " + _clean(r.get("error"))
    lines = [
        "🧪 V159 — Citation & Consistency Gate", "",
        f"وضعیت Gate: {r.get('status')}",
        f"خطاهای جدی: {r.get('counts', {}).get('high', 0)} | موارد متوسط: {r.get('counts', {}).get('medium', 0)} | موارد پایین: {r.get('counts', {}).get('low', 0)}",
        "",
        "V159 فقط کنترل می‌کند و متن را اصلاح نمی‌کند.",
    ]
    findings = r.get("findings") or []
    if findings:
        lines.append("")
        for f in findings[:max(1, limit)]:
            lines += [
                f"{str(f.get('severity', 'medium')).upper()} · {f.get('category')}",
                f"مکان: {f.get('location')}",
                f"⚠️ {f.get('problem')}",
                f"اقدام: {f.get('suggested_action') or 'بررسی دستی'}",
                "",
            ]
    else:
        lines += ["", "✅ کنترل‌های V159 بدون finding مسدودکننده عبور کردند."]
    lines += [
        "",
        "🔒 V159 محلی است؛ هیچ API خارجی استفاده نشده است.",
        "⚖️ عبور از Gate به معنی تأیید نهایی محتوای حقوقی نیست؛ بررسی و تأیید وکیل همچنان الزامی است.",
    ]
    return "\n".join(lines)
