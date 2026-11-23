# -*- coding: utf-8 -*-
"""V156 — local-first structured legal Draft Engine.

Consumes V149/V151-V155 outputs and renders a traceable draft.  It does not
invent facts, legal authorities, citations, requested relief, or outcomes.
Every substantive paragraph carries source references in the structured model.
"""
from __future__ import annotations

from .text_utils import clean_whitespace as _clean
import re
from typing import Any, Dict, List, Optional

from .db import get_case, get_case_documents, get_case_text
from .brief_planner import build_brief_plan
from .brief_templates import TEMPLATES
from .brief_writer import render_structured_brief
from .timeline_engine import build_case_chronology
from .issue_engine import build_case_issues
from .evidence_engine import build_evidence_matrix
from .authority_engine import build_case_authorities
from .strategy_engine import build_case_strategies




def _sentences(text: str, limit: int = 80) -> List[str]:
    out=[]; seen=set()
    for s in re.split(r"(?<=[؟.!؛])\s+|[\r\n]+", text or ""):
        s=_clean(s).strip("-•▪◦")
        if len(s) < 20 or s in seen: continue
        seen.add(s); out.append(s[:1200])
        if len(out)>=limit: break
    return out


def _request_sentences(text: str) -> List[str]:
    pats=r"خواسته|تقاضا|درخواست|محکومیت|الزام|رد دعوا|نقض|اصلاح|تخلیه|پرداخت|استرداد|رفع اثر"
    return [s for s in _sentences(text, 120) if re.search(pats,s,re.I)][:8]


def _authority_map(authorities: Dict[str,Any]) -> Dict[str,Dict[str,Any]]:
    return {str(a.get("authority_id")):a for a in authorities.get("authorities") or [] if a.get("authority_id")}


def _claim_map(evidence: Dict[str,Any]) -> Dict[str,Dict[str,Any]]:
    return {str(c.get("claim_id")):c for c in evidence.get("claims") or [] if c.get("claim_id")}


def _matrix_map(evidence: Dict[str,Any]) -> Dict[str,Dict[str,Any]]:
    return {str(m.get("claim_id")):m for m in evidence.get("matrix") or [] if m.get("claim_id")}


def _issue_map(issues: Dict[str,Any]) -> Dict[str,Dict[str,Any]]:
    return {str(i.get("issue_id")):i for i in issues.get("issues") or [] if i.get("issue_id")}


def _strategy_map(strategies: Dict[str,Any]) -> Dict[str,Dict[str,Any]]:
    return {str(s.get("issue_id")):s for s in strategies.get("strategies") or [] if s.get("issue_id")}


def _independent_evidence(matrix: Dict[str,Any]) -> List[Dict[str,Any]]:
    out=[]
    for e in matrix.get("evidence") or []:
        if e.get("origin"): continue
        if e.get("link_type") not in {"supports","contradicts"}: continue
        out.append(e)
    return out


def _verified_authorities_for_strategy(strategy: Dict[str,Any], auth_map: Dict[str,Dict[str,Any]]) -> List[Dict[str,Any]]:
    out=[]
    for aid in strategy.get("supporting_authorities") or []:
        a=auth_map.get(str(aid))
        if not a or a.get("verification_status") != "verified": continue
        if a.get("temporal_status") not in {"pre_or_same_event_date","unknown","bounded_but_case_date_unknown",None}: continue
        out.append(a)
    return out


def _facts_for_claim(claim: Dict[str,Any], matrix: Dict[str,Any]) -> List[Dict[str,Any]]:
    facts=[]
    # Only supporting evidence is promoted into the factual section.
    # Contradicting evidence remains traceable on the claim but must not be
    # silently presented as an established fact.
    # The V153 matrix row already identifies the claim. Do not search across
    # the case-wide evidence collection here, or evidence can leak between
    # unrelated claims.
    if str(matrix.get("claim_id")) != str(claim.get("claim_id")):
        return []
    for e in _independent_evidence(matrix):
        if e.get("link_type") != "supports":
            continue
        facts.append({
            "text":_clean(e.get("text")),
            "document_id":e.get("document_id"),
            "document_name":e.get("document_name"),
            "page":e.get("page"),
            "char_start":e.get("char_start"),
            "char_end":e.get("char_end"),
            "stance":e.get("link_type"),
            "source_refs":[x for x in (e.get("source_refs") or []) if x is not None],
        })
    return facts[:4]


def _authority_ref(a: Dict[str,Any], claim_id: Optional[str]=None) -> Dict[str,Any]:
    return {
        "authority_id":a.get("authority_id"),
        "claim_id":claim_id,
        "title":_clean(a.get("title")),
        "article_number":a.get("article_number"),
        "exact_text":_clean(a.get("text"))[:1600],
        "source_file":a.get("source_file"),
        "source_location":a.get("source_location"),
        "citation_key":a.get("citation_key"),
        "verification_status":a.get("verification_status"),
        "temporal_status":a.get("temporal_status"),
    }


def _build_argument(issue: Dict[str,Any], strategy: Dict[str,Any], evidence: Dict[str,Any], authorities: Dict[str,Any]) -> Dict[str,Any]:
    iid=str(issue.get("issue_id")); claims=[c for c in evidence.get("claims") or [] if str(c.get("issue_id"))==iid]
    cm=_claim_map(evidence); mm=_matrix_map(evidence); am=_authority_map(authorities)
    supporting_claims=[]; supporting_evidence=[]; authority_refs=[]; missing=[]; unsupported=[]
    for c in claims:
        cid=str(c.get("claim_id")); mat=mm.get(cid,{})
        ev=_facts_for_claim(c,mat)
        supporting_claims.append(cid)
        supporting_evidence.append({"claim_id":cid,"claim_text":_clean(c.get("claim_text")),"status":c.get("claim_status"),"evidence":ev})
        if not ev: missing.append({"type":"evidence","claim_id":cid,"text":"مدرک مستقل قابل ردیابی برای این ادعا در ماتریس فعلی کافی نیست."})
        if c.get("claim_status") in {"contradicted","mixed"}:
            unsupported.append({"claim_id":cid,"type":"contrary_evidence","text":"این ادعا در ماتریس ادله دارای نشانه مخالف یا متعارض است و نباید به‌صورت قطعی بیان شود."})
    for a in _verified_authorities_for_strategy(strategy,am):
        # Only attach an authority to a claim if V154 created a claim-specific link.
        links=[x for x in authorities.get("links") or [] if str(x.get("authority_id"))==str(a.get("authority_id")) and str(x.get("issue_id"))==iid]
        claim_links=[x for x in links if x.get("claim_id") is not None]
        if claims and not claim_links: continue
        if claim_links:
            for link in claim_links[:3]:
                ref=_authority_ref(a,str(link.get("claim_id")))
                ref["relation"]=link.get("relation")
                ref["link_verification_status"]=link.get("verification_status")
                ref["link_temporal_status"]=link.get("temporal_status")
                authority_refs.append(ref)
        else:
            # Issue-only authority links are intentionally not promoted to
            # claim support. They remain visible through V154/source_trace.
            continue
    if not authority_refs:
        missing.append({"type":"authority","issue_id":iid,"text":"منبع قانونی تأییدشده و قابل اتصال به ادعا در V154 برای این بخش کافی نیست."})
    theory=_clean((strategy.get("theory") or {}).get("text"))
    # Drafting rule: do not convert the strategy frame into a legal conclusion.
    application=("با توجه به ادعاها، مدارک و مستندات قانونیِ قابل ردیابی فوق، "
                 "این بخش برای بررسی و تکمیل استدلال توسط وکیل تنظیم شده است؛ "
                 "نتیجه حقوقی قطعی در این مرحله اعلام نمی‌شود.")
    return {
        "argument_id":f"arg-{iid or 'unknown'}",
        "issue_id":iid,
        "heading":_clean(issue.get("label")) or "مسئله حقوقی",
        "position":_clean(issue.get("question")),
        "claims":supporting_claims,
        "supporting_evidence":supporting_evidence,
        "authority_refs":authority_refs,
        "reasoning_steps":[
            {"step":"issue","text":_clean(issue.get("question")),"source_refs":[]},
            {"step":"strategy_frame","text":theory,"source_refs":[]},
            {"step":"application_frame","text":application,"source_refs":[x.get("authority_id") for x in authority_refs]},
        ],
        "counterargument_refs":strategy.get("counterarguments") or [],
        "unsupported_parts":unsupported,
        "missing_support":missing,
        "requires_lawyer_review":True,
    }


def _build_citations(arguments: List[Dict[str,Any]]) -> List[Dict[str,Any]]:
    citations=[]
    seen=set()
    for arg in arguments:
        for ref in arg.get("authority_refs") or []:
            aid=ref.get("authority_id")
            if not aid: continue
            key=(str(aid),str(arg.get("issue_id")),str(ref.get("claim_id")))
            if key in seen: continue
            seen.add(key)
            citations.append({
                "citation_id":f"cit-{len(citations)+1:04d}",
                "authority_id":aid,
                "claim_id":ref.get("claim_id"),
                "issue_id":arg.get("issue_id"),
                "citation_key":ref.get("citation_key"),
                "article_number":ref.get("article_number"),
                "exact_text":ref.get("exact_text"),
                "source_file":ref.get("source_file"),
                "source_location":ref.get("source_location"),
                "verification_status":ref.get("verification_status"),
                "temporal_status":ref.get("temporal_status"),
                "verification_required":ref.get("verification_status") != "verified" or ref.get("temporal_status") not in {"pre_or_same_event_date", "unknown", "bounded_but_case_date_unknown", None},
            })
    return citations


def _build_source_trace(chronology, issues, evidence, authorities, strategies, plan, arguments, citations):
    return {
        "v149_plan":plan,
        "v151_event_ids":[e.get("event_id") for e in chronology.get("events") or [] if e.get("event_id")],
        "v152_issue_ids":[i.get("issue_id") for i in issues.get("issues") or [] if i.get("issue_id")],
        "v153_claim_ids":[c.get("claim_id") for c in evidence.get("claims") or [] if c.get("claim_id")],
        "v154_authority_ids":[a.get("authority_id") for a in authorities.get("authorities") or [] if a.get("authority_id")],
        "v155_strategy_issue_ids":[s.get("issue_id") for s in strategies.get("strategies") or [] if s.get("issue_id")],
        "argument_ids":[a.get("argument_id") for a in arguments],
        "citation_ids":[c.get("citation_id") for c in citations],
    }

def build_case_draft(uid: int, cid: int, *, brief_type: str="لایحه دفاعیه", template_key: str="", include_review_notes: bool=True, analysis_context: Optional[Dict[str,Any]]=None, return_context: bool=False, confirmed_answers: Optional[Dict[str, str]]=None, confirmed_answer_labels: Optional[Dict[str, str]]=None) -> Dict[str,Any]:
    """Build V156 once and optionally expose its upstream analysis snapshot.

    The snapshot is an internal hand-off for V157/V158; callers should treat it
    as read-only. Keeping it in one pass prevents V157 from recomputing V151-V155
    and accidentally reviewing a different upstream state.
    """
    if analysis_context is None:
        case=get_case(uid,int(cid))
        if not case:
            return {"version":156,"case_id":int(cid),"draft":None,"api_used":False,"error":"case_not_found"}
        case_text=_clean(get_case_text(uid,int(cid)) or "")
        analysis_context={
            "case":case,
            "case_text":case_text,
            "chronology":build_case_chronology(uid,int(cid),include_undated=True),
            "issues":build_case_issues(uid,int(cid)),
            "evidence":build_evidence_matrix(uid,int(cid)),
            "authorities":build_case_authorities(uid,int(cid)),
            "strategies":build_case_strategies(uid,int(cid)),
            "plan":build_brief_plan(facts=case_text,brief_type=brief_type,case_text=case_text,template_key=template_key),
        }
    case=analysis_context.get("case") or get_case(uid,int(cid))
    if not case:
        return {"version":156,"case_id":int(cid),"draft":None,"api_used":False,"error":"case_not_found"}
    case_text=_clean(analysis_context.get("case_text") or get_case_text(uid,int(cid)) or "")
    chronology=analysis_context.get("chronology") or {}
    issues=analysis_context.get("issues") or {}
    evidence=analysis_context.get("evidence") or {}
    authorities=analysis_context.get("authorities") or {}
    strategies=analysis_context.get("strategies") or {}
    plan=analysis_context.get("plan") or build_brief_plan(facts=case_text,brief_type=brief_type,case_text=case_text,template_key=template_key)
    strat_by=_strategy_map(strategies)

    arguments=[]
    for issue in issues.get("issues") or []:
        arguments.append(_build_argument(issue,strat_by.get(str(issue.get("issue_id")),{}),evidence,authorities))

    facts=[]; seen=set()
    # Prefer independent evidence over raw case prose; raw prose is retained only as review leads.
    for arg in arguments:
        for item in arg.get("supporting_evidence") or []:
            for e in item.get("evidence") or []:
                key=(e.get("document_id"),e.get("char_start"),e.get("char_end"),e.get("text"))
                if key in seen: continue
                seen.add(key); facts.append(e)
    for event in (chronology.get("events") or [])[:30]:
        # Timeline status is authoritative here: only explicitly verified events
        # may enter the factual chronology section. Assertions/uncertain events
        # remain upstream review signals and are not promoted to facts.
        if event.get("status") != "verified": continue
        text=_clean(event.get("description") or event.get("title"))
        if not text: continue
        facts.append({"text":text,"event_id":event.get("event_id"),"date":event.get("date"),"status":event.get("status"),"source_refs":[s.get("document_id") for s in event.get("sources") or []]})
        if len(facts)>=40: break

    requests=_request_sentences(case_text)
    warnings=[]
    if plan.get("missing"): warnings.append({"type":"missing_information","items":plan.get("missing")[:10]})
    if authorities.get("warnings"): warnings.append({"type":"authority_review","items":authorities.get("warnings")[:10]})
    for a in arguments:
        if a.get("missing_support"): warnings.append({"type":"argument_gap","issue_id":a.get("issue_id"),"items":a.get("missing_support")[:5]})
    if not requests: warnings.append({"type":"requested_relief_missing","items":["خواسته/تقاضای صریح در متن پرونده پیدا نشد؛ قبل از نهایی‌سازی تکمیل شود."]})

    citations=_build_citations(arguments)
    used_authority_ids={str(c.get("authority_id")) for c in citations if c.get("authority_id")}
    confirmed_inputs = []
    for key, value in (confirmed_answers or {}).items():
        value = _clean(value)
        if not value:
            continue
        confirmed_inputs.append({
            "key": str(key),
            "label": _clean((confirmed_answer_labels or {}).get(str(key)) or str(key)),
            "value": value[:3000],
            "source": "lawyer_confirmed_input",
            "source_label": "ورودی صریح و تأییدشده وکیل",
            "confirmed_by_lawyer": True,
            "is_independently_verified": False,
        })
    draft={
        "draft_id":f"dr-{int(cid)}-156",
        "case_id":int(cid),
        "case_name":_clean(case.get("file_name")),
        "draft_type":_clean(brief_type) or "لایحه دفاعیه",
        "template_key":template_key or "",
        "template_title":_clean(TEMPLATES.get(template_key,{}).get("title")) if template_key else "",
        "caption":{"court":None,"parties":plan.get("parties",[])[:8],"subject":plan.get("purpose")},
        "facts":facts,
        "issues":[{"issue_id":i.get("issue_id"),"label":i.get("label"),"question":i.get("question"),"status":i.get("status")} for i in issues.get("issues") or []],
        "arguments":arguments,
        "authorities":[_authority_ref(a) for a in authorities.get("authorities") or [] if a.get("verification_status")=="verified" and str(a.get("authority_id")) in used_authority_ids],
        "citations":citations,
        "requested_relief":requests,
        "missing_information":plan.get("missing",[])[:10],
        "lawyer_confirmed_inputs": confirmed_inputs,
        "missing_authorities":[w for w in warnings if w.get("type")=="authority_review"],
        "warnings":warnings if include_review_notes else [],
        "source_trace":_build_source_trace(chronology,issues,evidence,authorities,strategies,plan,arguments,citations),
        "review_status":"draft_requires_lawyer_review",
        "requires_lawyer_review":True,
        "legal_conclusion_generated":False,
        "final_brief_generated":False,
    }
    draft["rendered_text"] = render_structured_brief(draft)
    result={"version":156,"case_id":int(cid),"case_name":_clean(case.get("file_name")),"draft":draft,"api_used":False,"resolver_path":["case_db","v149_brief_plan","v151_chronology","v152_issue_map","v153_evidence_matrix","v154_authority_engine","v155_strategy_engine","structured_draft","legacy_brief_writer_bridge"],"legal_conclusion_generated":False,"final_brief_generated":False}
    if return_context:
        result["analysis_context"] = analysis_context
    return result


def render_case_draft(result: Dict[str,Any], max_arguments: int=8) -> str:
    d=(result or {}).get("draft") or {}
    if not d: return "❌ پیش‌نویس ساختاری در دسترس نیست."
    lines=["📝 پیش‌نویس ساختاری V156", "", f"نوع: {d.get('draft_type') or 'لایحه دفاعیه'}"]
    if d.get("template_title"): lines.append(f"قالب: {d['template_title']}")
    lines += ["", "📌 شرح مستند پرونده:"]
    for f in (d.get("facts") or [])[:8]:
        src=f.get("document_name") or ("رویداد " + str(f.get("event_id")) if f.get("event_id") else "منبع پرونده")
        page=f"، ص.{f.get('page')}" if f.get("page") else ""
        lines.append(f"• {_clean(f.get('text'))[:650]} [{src}{page}]")
    lines += ["", "🎯 مسائل و استدلال‌های قابل بازبینی:"]
    for a in (d.get("arguments") or [])[:max(1,max_arguments)]:
        lines += ["", f"### {_clean(a.get('heading'))}", f"مسئله: {_clean(a.get('position'))[:500]}"]
        for se in (a.get("supporting_evidence") or [])[:2]:
            lines.append(f"📎 {_clean(se.get('claim_text'))[:300]} — وضعیت: {se.get('status')}")
            for e in (se.get("evidence") or [])[:2]: lines.append(f"   ↳ {_clean(e.get('text'))[:280]}")
        for ar in (a.get("authority_refs") or [])[:3]:
            loc=f" — {ar.get('article_number')}" if ar.get('article_number') else ""
            lines.append(f"⚖️ {ar.get('title') or 'منبع قانونی'}{loc}")
        for gap in (a.get("missing_support") or [])[:2]: lines.append(f"⚠️ {gap.get('text')}")
        lines.append("🧭 نتیجه قطعی تولید نشده؛ نحوه اعمال و نتیجه باید توسط وکیل تکمیل و تأیید شود.")
    if d.get("requested_relief"):
        lines += ["", "📮 خواسته/تقاضای صریح استخراج‌شده:"]
        lines += [f"• {_clean(x)[:500]}" for x in d["requested_relief"][:6]]
    if d.get("warnings"):
        lines += ["", "⚠️ موارد بازبینی قبل از نهایی‌سازی:"]
        for w in d["warnings"][:6]: lines.append(f"• {w.get('type')}: {_clean(w.get('items'))[:500]}")
    lines += ["", "🔒 V156: متن بر پایه خروجی‌های V149 و V151→V155 ساخته شده؛ API خارجی استفاده نشد.", "⚠️ این خروجی پیش‌نویس داخلی است و قبل از ارائه باید توسط وکیل بررسی و نهایی شود."]
    return "\n".join(lines)
