# -*- coding: utf-8 -*-
"""V155 — local-first Defense Strategy Engine."""
from __future__ import annotations

from .text_utils import clean_whitespace as _clean
import re
from typing import Any, Dict, List, Optional
from .db import get_case
from .issue_engine import build_case_issues
from .evidence_engine import build_evidence_matrix
from .authority_engine import build_case_authorities
from .brief_workspace import extract_opposing_claims

def _issue_claims(ev, iid): return [c for c in ev.get("claims",[]) if str(c.get("issue_id"))==str(iid)]
def _matrix_for(ev,cid): return next((r for r in ev.get("matrix",[]) if str(r.get("claim_id"))==str(cid)),{})
def _weak_points(claims, ev):
    out=[]
    for c in claims:
        m=_matrix_for(ev,c.get("claim_id")); st=c.get("claim_status")
        if m.get("evidence_gap") or st=="unsupported": out.append({"claim_id":c.get("claim_id"),"type":"evidence_gap","text":"برای این ادعا مدرک مستقل و قابل ردیابی کافی در ماتریس فعلی ثبت نشده است."})
        if st in {"mixed","contradicted"}: out.append({"claim_id":c.get("claim_id"),"type":"contrary_evidence","text":"برای این ادعا نشانه یا مدرک مخالف نیز در پرونده ثبت شده است و باید با اصل اسناد بررسی شود."})
    return out

def _missing_evidence(claims,ev):
    return [{"claim_id":c.get("claim_id"),"request":f"مدرک مستقل برای ادعای «{_clean(c.get('claim_text'))[:240]}» شناسایی/ارائه شود."} for c in claims if _matrix_for(ev,c.get("claim_id")).get("evidence_gap")]

def _authority_gaps(auth,iid):
    issue=next((x for x in auth.get("issues",[]) if str(x.get("issue_id"))==str(iid)),{})
    out=[]
    if issue.get("authority_gap"): out.append({"issue_id":iid,"type":"primary_authority_gap","request":"منبع اصلی قانونی قابل اتکا برای این مسئله پیدا/تأیید نشده است."})
    if issue.get("authority_review_required"): out.append({"issue_id":iid,"type":"authority_review","request":"وضعیت منبع یا اعتبار زمانی دست‌کم یک مستند قانونی نیازمند بازبینی است."})
    return out

def _verified_authorities(auth,iid,claims):
    ids={str(c.get("claim_id")) for c in claims}; out=[]
    for link in auth.get("links",[]):
        if (str(link.get("issue_id"))==str(iid)
            and ((ids and str(link.get("claim_id")) in ids) or (not ids and link.get("claim_id") is None))
            and link.get("authority_id")
            and link.get("verification_status")=="verified"
            and link.get("temporal_status") in {"pre_or_same_event_date", "unknown", "bounded_but_case_date_unknown", None}):
            out.append(link["authority_id"])
    return list(dict.fromkeys(out))

def _authority_refs(auth,iid,claims):
    ids={str(c.get("claim_id")) for c in claims}; out=[]
    for link in auth.get("links",[]):
        if (str(link.get("issue_id"))==str(iid)
            and (str(link.get("claim_id")) in ids or link.get("claim_id") is None)
            and link.get("authority_id")):
            out.append({
                "authority_id":link.get("authority_id"),
                "claim_id":link.get("claim_id"),
                "verification_status":link.get("verification_status"),
                "temporal_status":link.get("temporal_status"),
                "relation":link.get("relation") or "candidate_authority",
            })
    seen=set(); dedup=[]
    for x in out:
        key=(x["authority_id"],x.get("claim_id"),x.get("relation"))
        if key not in seen:
            seen.add(key); dedup.append(x)
    return dedup

def _counterarguments(issue,claims,ev,opposing_claims=None):
    out=[]
    for x in (issue.get("contrary_signals") or [])[:5]: out.append({"type":"documented_contrary_signal","text":_clean(x.get("text")),"response_required":True})
    for c in claims:
        if c.get("claim_status") in {"mixed","contradicted"}:
            for e in [e for e in _matrix_for(ev,c.get("claim_id")).get("evidence",[]) if e.get("link_type")=="contradicts" and not e.get("origin")][:3]: out.append({"type":"contrary_evidence","claim_id":c.get("claim_id"),"text":_clean(e.get("text")),"response_required":True})
    for x in (opposing_claims or [])[:8]: out.append({"type":"opponent_brief_claim","text":_clean(x),"response_required":True})
    return out

def build_strategy_for_issue(issue: Dict[str,Any], evidence: Dict[str,Any], authorities: Dict[str,Any], *, opposing_claims: Optional[List[str]]=None):
    iid=str(issue.get("issue_id") or ""); claims=_issue_claims(evidence,iid); weak=_weak_points(claims,evidence); missing=_missing_evidence(claims,evidence); ag=_authority_gaps(authorities,iid); va=_verified_authorities(authorities,iid,claims); arefs=_authority_refs(authorities,iid,claims); counters=_counterarguments(issue,claims,evidence,opposing_claims)
    flags=[]
    if weak: flags.append("evidence_weakness")
    if ag: flags.append("authority_gap_or_review")
    if counters: flags.append("counterargument_review")
    if any(c.get("claim_status")=="contradicted" for c in claims): flags.append("contradicted_claim")
    if not va: flags.append("no_verified_authority_link")
    return {
      "strategy_id":f"str-{iid or 'unknown'}","issue_id":iid,"objective":_clean(issue.get("question")) or "مسئله پرونده برای بررسی حقوقی",
      "theory":{"type":"review_frame","text":"این چارچوب باید بر پاسخ مستند به مسئله، با اتکا به ادعاهای قابل ردیابی، ادله مستقل و منابع قانونی تأییدشده بنا شود؛ نتیجه حقوقی نهایی تولید نشده است."},
      "supporting_claims":[c.get("claim_id") for c in claims],
      "supporting_evidence":[{"claim_id":c.get("claim_id"),"evidence_count":_matrix_for(evidence,c.get("claim_id")).get("independent_evidence_count",0),"status":c.get("claim_status")} for c in claims],
      "supporting_authorities":va,
      "authority_refs":arefs,
      "weak_points":weak,"missing_evidence":missing,"missing_authorities":ag,"counterarguments":counters,"responses":[],"risk_flags":flags,
      "coverage_signal":round(min(1.0,.45+.05*len(claims)+.04*len(va)-.06*len(weak)),3),
      "requires_lawyer_review":True,"legal_conclusion_generated":False}

def build_case_strategies(uid:int,cid:int,*,opposing_brief:str=""):
    case=get_case(uid,int(cid))
    if not case: return {"version":155,"case_id":int(cid),"strategies":[],"api_used":False,"error":"case_not_found"}
    issues=build_case_issues(uid,int(cid)); ev=build_evidence_matrix(uid,int(cid)); auth=build_case_authorities(uid,int(cid)); opp=extract_opposing_claims(opposing_brief) if opposing_brief else []
    strategies=[build_strategy_for_issue(i,ev,auth,opposing_claims=opp) for i in issues.get("issues",[])]
    return {"version":155,"case_id":int(cid),"case_name":_clean(case.get("file_name")),"strategies":strategies,"counts":{"issues":len(strategies),"with_evidence_gaps":sum(bool(s["missing_evidence"]) for s in strategies),"with_authority_gaps":sum(bool(s["missing_authorities"]) for s in strategies),"with_counterarguments":sum(bool(s["counterarguments"]) for s in strategies),"lawyer_review_required":len(strategies)},"opponent_claims":opp,"api_used":False,"resolver_path":["case_db","v152_issue_map","v153_evidence_matrix","v154_authority_engine","strategy_frame","counterargument_signals","gap_flags"],"legal_conclusion_generated":False,"final_brief_generated":False,"strategy_confidence":None}

def format_case_strategies(result:Dict[str,Any],limit:int=8):
    r=result or {}; c=r.get("counts") or {}; rows=r.get("strategies") or []
    lines=["🛡️ نقشه استراتژی دفاعی پرونده","",f"مسائل: {c.get('issues',0)} | خلأ مدرک: {c.get('with_evidence_gaps',0)} | خلأ منبع قانونی: {c.get('with_authority_gaps',0)} | موارد نیازمند پاسخ: {c.get('with_counterarguments',0)}","","این خروجی «چارچوب بررسی استراتژی» است؛ نتیجه قطعی دعوا، استدلال نهایی یا پیش‌بینی رأی تولید نمی‌کند."]
    for s in rows[:max(1,limit)]:
        lines += ["",f"🎯 {_clean(s.get('objective'))[:360]}",f"ادعا: {len(s.get('supporting_claims') or [])} | منبع قانونی تأییدشده: {len(s.get('supporting_authorities') or [])}",f"ریسک‌ها: {', '.join(s.get('risk_flags') or []) or '—'}"]
        for w in (s.get("weak_points") or [])[:2]: lines.append(f"⚠️ {_clean(w.get('text'))[:260]}")
        for m in (s.get("missing_evidence") or [])[:2]: lines.append(f"📎 {_clean(m.get('request'))[:260]}")
        for a in (s.get("missing_authorities") or [])[:2]: lines.append(f"⚖️ {_clean(a.get('request'))[:260]}")
        for x in (s.get("counterarguments") or [])[:2]: lines.append(f"↔️ {_clean(x.get('text'))[:260]}")
    lines += ["","🔒 مسیر: V152 → V153 → V154 → V155 | API خارجی: استفاده نشد"]
    return "\n".join(lines)
