# -*- coding: utf-8 -*-
"""V157 — local-first adversarial review of the structured V156 draft.

This engine is a review layer, not a legal decision-maker. It surfaces factual,
evidentiary, authority, logic, coverage, citation and procedural gaps using only
traceable upstream data. It never invents rebuttals or predicts outcomes.
"""
from __future__ import annotations

from .text_utils import clean_whitespace as _clean
import re
from typing import Any, Dict

from .draft_engine import build_case_draft
from .timeline_engine import build_case_chronology
from .issue_engine import build_case_issues
from .evidence_engine import build_evidence_matrix
from .authority_engine import build_case_authorities
from .strategy_engine import build_case_strategies

SEVERITIES = {"high", "medium", "low"}
CATEGORIES = {
    "FACT_UNSUPPORTED", "FACT_CONTRADICTION", "EVIDENCE_GAP", "AUTHORITY_GAP",
    "AUTHORITY_MISMATCH", "TEMPORAL_AUTHORITY_RISK", "CITATION_GAP", "CITATION_MISMATCH",
    "LOGICAL_GAP", "COUNTERARGUMENT_MISSING", "ISSUE_MISSING", "PROCEDURAL_GAP",
    "REQUEST_MISMATCH", "INTERNAL_INCONSISTENCY", "AMBIGUOUS_LANGUAGE", "UNSUPPORTED_CONCLUSION",
}


def _add(out, category, severity, location, text, problem, why, refs=None, action="", lawyer=True):
    out.append({
        "finding_id": f"f-{len(out)+1:04d}", "category": category,
        "severity": severity if severity in SEVERITIES else "medium", "location": location or "draft",
        "text": _clean(text), "problem": _clean(problem), "why_it_matters": _clean(why),
        "source_refs": list(refs or []), "suggested_action": _clean(action),
        "requires_lawyer_review": bool(lawyer),
    })

def _maps(draft):
    claims={str(c.get("claim_id")):c for a in draft.get("arguments",[]) for c in [{"claim_id":x} for x in a.get("claims",[])]}
    issues={str(i.get("issue_id")):i for i in draft.get("issues",[]) if i.get("issue_id")}
    return issues, claims

def _review_facts(draft, chronology, evidence, out):
    verified={str(e.get("event_id")) for e in chronology.get("events",[]) if e.get("status") == "verified"}
    claim_status={str(c.get("claim_id")):c.get("claim_status") for c in evidence.get("claims",[])}
    for i,f in enumerate(draft.get("facts",[]),1):
        eid=f.get("event_id")
        if eid and str(eid) not in verified:
            _add(out,"FACT_UNSUPPORTED","high",f"facts[{i}]",f.get("text"),"این واقعیت در Draft با رویداد تأییدشده متناظر نیست.","ممکن است یک گزاره بررسی‌نشده به‌عنوان واقعیت قطعی ارائه شود.",[eid],"وضعیت رویداد و منبع اصلی را بررسی کنید.")
    for a in draft.get("arguments",[]):
        for part in a.get("unsupported_parts",[]):
            cid=part.get("claim_id"); _add(out,"FACT_CONTRADICTION","high",a.get("argument_id"),part.get("text"),"ادعا در ماتریس ادله دارای وضعیت متعارض است.","بیان قطعی می‌تواند با بخشی از سوابق پرونده ناسازگار باشد.",[cid],"اصل اسناد مؤید و مخالف را کنار هم بررسی کنید.")
        for se in a.get("supporting_evidence",[]):
            if not se.get("evidence"):
                _add(out,"EVIDENCE_GAP","high",a.get("argument_id"),se.get("claim_text"),"برای این ادعا مدرک مستقل در Draft متصل نشده است.","ادعای بدون پشتوانه ردیابی‌شده قابل اتکا نیست.",[se.get("claim_id")],"مدرک مستقل را اضافه یا ادعا را محدود کنید.")

def _review_authorities(draft, authorities, out):
    amap={str(a.get("authority_id")):a for a in authorities.get("authorities",[]) if a.get("authority_id")}
    for a in draft.get("arguments",[]):
        for ref in a.get("authority_refs",[]):
            aid=str(ref.get("authority_id")); src=amap.get(aid)
            if not src:
                _add(out,"AUTHORITY_MISMATCH","high",a.get("argument_id"),ref.get("title"),"مرجع قانونی Draft در رجیستری V154 پیدا نشد.","قابلیت راستی‌آزمایی و ردیابی منبع از بین می‌رود.",[aid],"شناسه و منبع قانونی را دوباره بررسی کنید.")
            elif src.get("verification_status") != "verified":
                _add(out,"AUTHORITY_GAP","high",a.get("argument_id"),src.get("title"),"منبع قانونی متصل، تأییدشده نیست.","منبع تأییدنشده نباید به‌عنوان پشتوانه قطعی استفاده شود.",[aid],"وضعیت منبع را در V154 بررسی و تأیید کنید.")
            if ref.get("temporal_status") not in {"pre_or_same_event_date","unknown","bounded_but_case_date_unknown",None}:
                _add(out,"TEMPORAL_AUTHORITY_RISK","high",a.get("argument_id"),src.get("title") if src else ref.get("title"),"وضعیت زمانی منبع قانونی با پرونده نیازمند بررسی است.","ممکن است منبع در بازه زمانی مرتبط قابل اعمال نباشد.",[aid],"تاریخ نفاذ و تاریخ رویداد مرتبط را کنترل کنید.")
    if not draft.get("authorities") and draft.get("issues"):
        _add(out,"AUTHORITY_GAP","high","authorities","","برای Draft هیچ منبع قانونی تأییدشده‌ای ثبت نشده است.","بخش استدلال حقوقی بدون مستند قانونی قابل تکمیل نیست.",[],"منابع اصلی مرتبط را در V154 تأیید کنید.")



def _review_citations(draft, authorities, out):
    amap={str(a.get("authority_id")):a for a in authorities.get("authorities",[]) if a.get("authority_id")}
    citations=draft.get("citations") or []
    refs={(str(r.get("authority_id")),str(r.get("claim_id")),str(a.get("issue_id")))
          for a in draft.get("arguments",[]) for r in a.get("authority_refs",[])}
    if draft.get("arguments") and not citations and any(a.get("authority_refs") for a in draft.get("arguments",[])):
        _add(out,"CITATION_GAP","high","citations","","برای مراجع متصل به استدلال، citation ساختاری ثبت نشده است.","ردیابی دقیق استناد تا ادعا/مسئله دشوار می‌شود.",[],"برای هر مرجع استفاده‌شده citation ساختاری ایجاد کنید.")
    for c in citations:
        aid=str(c.get("authority_id")); src=amap.get(aid)
        if not src:
            _add(out,"CITATION_MISMATCH","high",c.get("citation_id"),c.get("exact_text"),"citation به مرجع ثبت‌شده در V154 متصل نیست.","امکان راستی‌آزمایی منبع و متن استناد از بین می‌رود.",[aid],"شناسه authority را با V154 تطبیق دهید.")
        if not c.get("exact_text") and not c.get("article_number") and not c.get("citation_key"):
            _add(out,"CITATION_GAP","medium",c.get("citation_id"),"","citation اطلاعات کافی برای بازیابی منبع ندارد.","وکیل نمی‌تواند به‌سادگی محل دقیق استناد را کنترل کند.",[aid],"شماره ماده، citation key یا متن دقیق و محل منبع را تکمیل کنید.")
        if c.get("verification_status") != "verified":
            _add(out,"AUTHORITY_GAP","high",c.get("citation_id"),c.get("exact_text") or c.get("citation_key"),"citation به منبع تأییدنشده متصل است.","منبع تأییدنشده نباید به‌عنوان پشتوانه نهایی تلقی شود.",[aid],"وضعیت منبع را در V154 بررسی کنید.")


def _review_traceability(draft, out):
    trace=draft.get("source_trace") or {}
    required=("v149_plan","v151_event_ids","v152_issue_ids","v153_claim_ids","v154_authority_ids","v155_strategy_issue_ids","argument_ids")
    missing=[k for k in required if k not in trace]
    if missing:
        _add(out,"INTERNAL_INCONSISTENCY","high","source_trace",", ".join(missing),"ردیابی بین لایه‌های V149 تا V156 ناقص است.","V157 و V158 ممکن است نتوانند منشأ یک بخش Draft را مشخص کنند.",missing,"source_trace را با شناسه‌های upstream کامل کنید.")
    for a in draft.get("arguments",[]):
        if not a.get("reasoning_steps"):
            _add(out,"LOGICAL_GAP","medium",a.get("argument_id"),"","Argument بدون مسیر reasoning ثبت شده است.","مسیر مسئله تا استدلال برای بازبینی وکیل شفاف نیست.",[a.get("issue_id")],"مراحل استدلالی را تکمیل و به منابع upstream متصل کنید.")


def _review_conclusions(draft, out):
    if draft.get("legal_conclusion_generated") is True or draft.get("final_brief_generated") is True:
        _add(out,"UNSUPPORTED_CONCLUSION","high","draft","","Draft خود را به‌عنوان نتیجه حقوقی/نسخه نهایی علامت‌گذاری کرده است.","ممکن است خروجی بازبینی‌نشده به‌عنوان نتیجه نهایی تلقی شود.",[],"پرچم‌ها را بررسی و خروجی را در وضعیت review نگه دارید.")
    risky=re.compile(r"محکوم خواهد شد|حتماً پیروز|قطعاً|قطعا|مسلماً|بدون تردید|نتیجه قطعی|مسلماً")
    for a in draft.get("arguments",[]):
        for step in a.get("reasoning_steps",[]):
            text=_clean(step.get("text"))
            if risky.search(text) and not step.get("source_refs"):
                _add(out,"UNSUPPORTED_CONCLUSION","high",a.get("argument_id"),text,"عبارت نتیجه‌محور بدون source reference در reasoning آمده است.","ممکن است استنتاجی بدون مسیر قابل راستی‌آزمایی وارد Draft شده باشد.",[],"عبارت را به چارچوب بررسی مشروط تبدیل و منبع آن را ثبت کنید.")

def _review_coverage(draft, issues, evidence, strategies, out):
    did={str(i.get("issue_id")) for i in draft.get("issues",[]) if i.get("issue_id")}
    sid={str(s.get("issue_id")) for s in strategies.get("strategies",[]) if s.get("issue_id")}
    for iid in sid-did:
        _add(out,"ISSUE_MISSING","high", "issues", iid,"یک مسئله upstream در Draft دیده نمی‌شود.","ممکن است بخشی از دامنه پرونده در پیش‌نویس حذف شده باشد.",[iid],"مسئله را به Draft برگردانید.")
    argids={str(a.get("issue_id")) for a in draft.get("arguments",[]) if a.get("issue_id")}
    for iid in did-argids:
        _add(out,"ISSUE_MISSING","high","arguments",iid,"برای این مسئله بخش استدلالی وجود ندارد.","Issue بدون مسیر استدلالی در Draft باقی مانده است.",[iid],"یک argument ساختاری برای مسئله ایجاد کنید.")
    important={str(c.get("claim_id")) for c in evidence.get("claims",[]) if c.get("claim_status") in {"supported","mixed","contradicted"}}
    covered={str(cid) for a in draft.get("arguments",[]) for cid in a.get("claims",[])}
    for cid in sorted(important-covered):
        _add(out,"EVIDENCE_GAP","medium","arguments",cid,"یک ادعای مهم V153 در Draft پوشش داده نشده است.","ممکن است ارتباط ادعا و استدلال قطع شده باشد.",[cid],"ادعا و وضعیت مدرک آن را بررسی کنید.")
    if strategies.get("strategies") and not draft.get("arguments"):
        _add(out,"LOGICAL_GAP","high","arguments","","استراتژی‌های V155 وجود دارند اما argument در Draft ساخته نشده است.","Draft نمی‌تواند مسیر استراتژی تا متن را نشان دهد.",[],"اتصال V155→V156 را بررسی کنید.")

def _review_counterarguments(draft, strategies, out):
    for s in strategies.get("strategies",[]):
        iid=str(s.get("issue_id")); counters=s.get("counterarguments") or []
        if not counters: continue
        a=next((x for x in draft.get("arguments",[]) if str(x.get("issue_id"))==iid),None)
        if not a or not a.get("counterargument_refs"):
            _add(out,"COUNTERARGUMENT_MISSING","medium",iid,"","برای این مسئله upstream سیگنال مخالف وجود دارد اما در Draft ثبت نشده است.","حمله محتمل طرف مقابل ممکن است در بازبینی نادیده بماند.",[iid],"سیگنال مخالف را در بخش counterargument مرور کنید.")

def _review_requests(draft, case_text, out):
    if not draft.get("requested_relief"):
        _add(out,"PROCEDURAL_GAP","high","requested_relief","","خواسته/تقاضای روشن در Draft وجود ندارد.","بدون خواسته روشن، بررسی هم‌راستایی نتیجه و متن ممکن نیست.",[],"خواسته را از پرونده استخراج و توسط وکیل تأیید کنید.")
    else:
        text=_clean(case_text)
        if text and not any(_clean(r)[:80] in text for r in draft.get("requested_relief",[]) if _clean(r)):
            _add(out,"REQUEST_MISMATCH","medium","requested_relief"," | ".join(draft.get("requested_relief",[])[:3]),"خواسته استخراج‌شده نیازمند تطبیق با متن پرونده است.","خواسته ممکن است از زمینه ناقص یا مبهم استخراج شده باشد.",[],"خواسته و مستند اصلی آن را دستی کنترل کنید.")

def _review_ambiguity(draft, out):
    risky=re.compile(r"قطعا|حتما|بدیهی است|قطعاً|مسلماً|بدون تردید|محکوم خواهد شد|حتماً پیروز")
    for a in draft.get("arguments",[]):
        for step in a.get("reasoning_steps",[]):
            t=_clean(step.get("text"))
            if risky.search(t):
                _add(out,"AMBIGUOUS_LANGUAGE","medium",a.get("argument_id"),t,"عبارت بیش از حد قطعی یا نتیجه‌محور است.","ممکن است وضعیت بررسی‌نشده را به نتیجه قطعی تبدیل کند.",[],"عبارت را به زبان مشروط و مستند بازنویسی کنید.")

def review_structured_draft(draft: Dict[str,Any], *, chronology=None, evidence=None, authorities=None, strategies=None, case_text="") -> Dict[str,Any]:
    chronology=chronology or {}; evidence=evidence or {}; authorities=authorities or {}; strategies=strategies or {}
    out=[]
    if not draft:
        _add(out,"INTERNAL_INCONSISTENCY","high","draft","","Draft خالی است.","هیچ work product قابل ممیزی وجود ندارد.",[],"V156 را دوباره اجرا کنید.")
    else:
        _review_facts(draft,chronology,evidence,out)
        _review_authorities(draft,authorities,out)
        _review_citations(draft,authorities,out)
        _review_traceability(draft,out)
        _review_conclusions(draft,out)
        _review_coverage(draft,{str(i.get("issue_id")):i for i in draft.get("issues",[])},evidence,strategies,out)
        _review_counterarguments(draft,strategies,out)
        _review_requests(draft,case_text,out)
        _review_ambiguity(draft,out)
        if not draft.get("requires_lawyer_review", True):
            _add(out,"INTERNAL_INCONSISTENCY","high","draft","","Draft خود را نیازمند بازبینی وکیل اعلام نکرده است.","V157 نباید خروجی حقوقی را خودکار نهایی تلقی کند.",[],"پرچم review را اجباری نگه دارید.")
    counts={s:sum(1 for f in out if f["severity"]==s) for s in SEVERITIES}
    bycat={c:sum(1 for f in out if f["category"]==c) for c in sorted(CATEGORIES) if any(f["category"]==c for f in out)}
    return {"version":157,"findings":out,"counts":counts,"by_category":bycat,"requires_lawyer_review":True,"overall_quality_score":None,"winner":None,"prediction":None,"api_used":False,"review_complete":True}

def build_case_adversarial_review(uid:int,cid:int,*,brief_type="لایحه دفاعیه",confirmed_answers=None,confirmed_answer_labels=None) -> Dict[str,Any]:
    # V156 already computes the complete upstream snapshot. Reuse it rather
    # than rebuilding V151-V155 and risking a review against a different state.
    draft_result=build_case_draft(uid,cid,brief_type=brief_type,return_context=True,confirmed_answers=confirmed_answers,confirmed_answer_labels=confirmed_answer_labels)
    if draft_result.get("error"):
        return {"version":157,"case_id":int(cid),"draft":None,"findings":[],"error":draft_result["error"],"api_used":False}
    ctx=draft_result.get("analysis_context") or {}
    chronology=ctx.get("chronology") or {}
    evidence=ctx.get("evidence") or {}
    authorities=ctx.get("authorities") or {}
    strategies=ctx.get("strategies") or {}
    case_text=ctx.get("case_text") or ""
    review=review_structured_draft(draft_result.get("draft") or {},chronology=chronology,evidence=evidence,authorities=authorities,strategies=strategies,case_text=case_text)
    review.update({"case_id":int(cid),"draft":draft_result.get("draft"),"resolver_path":["v156_structured_draft","shared_v149_v155_analysis_context","v157_adversarial_review"]})
    return review

def render_adversarial_review(result:Dict[str,Any],limit:int=18)->str:
    r=result or {}; fs=r.get("findings") or []
    if r.get("error"): return "❌ بررسی خصمانه انجام نشد: "+_clean(r.get("error"))
    lines=["🛡️ V157 — بازبینی خصمانه پیش‌نویس","",f"یافته‌ها: {len(fs)} | بالا: {r.get('counts',{}).get('high',0)} | متوسط: {r.get('counts',{}).get('medium',0)} | پایین: {r.get('counts',{}).get('low',0)}","","این خروجی امتیاز کیفیت یا پیش‌بینی نتیجه نیست؛ فقط نقاط قابل حمله و موارد نیازمند بررسی را نشان می‌دهد."]
    for f in fs[:max(1,limit)]:
        lines += ["",f"{f.get('severity','medium').upper()} · {f.get('category')}",f"مکان: {f.get('location')}",f"⚠️ {f.get('problem')}",f"چرا مهم است: {f.get('why_it_matters')}",f"اقدام پیشنهادی: {f.get('suggested_action') or 'بررسی دستی'}"]
    if not fs: lines += ["","✅ در بررسی ساختاری فعلی یافته‌ای ثبت نشد؛ این به‌معنای تأیید نهایی لایحه نیست."]
    lines += ["","🔒 V157: بررسی محلی و بدون API خارجی انجام شد.","⚖️ نهایی‌سازی و تصمیم حقوقی همچنان با وکیل است."]
    return "\n".join(lines)
