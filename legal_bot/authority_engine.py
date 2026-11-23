# -*- coding: utf-8 -*-
"""V154 — local-first Legal Authority Engine.

Maps V152 issues and V153 claims to traceable legal authorities using the
existing local legal retrieval corpus.  This layer retrieves and verifies
source metadata; it does not generate a legal conclusion or decide whether an
authority legally controls a case.
"""
from __future__ import annotations

from .text_utils import clean_whitespace as _clean

import re
from datetime import date
from typing import Any, Dict, Iterable, List, Optional

from .db import get_case
from .issue_engine import build_case_issues
from .evidence_engine import build_evidence_matrix
from .laws import search_legal_research
from .calendar_dates import parse_jalali, parse_gregorian

AUTHORITY_TYPES = {
    "law": "STATUTE",
    "ruling": "JUDICIAL_DECISION",
    "consultation": "LEGAL_OPINION",
    "circular": "CIRCULAR",
    "sample": "SECONDARY_SOURCE",
}

TYPE_PRIORITY = {
    "STATUTE": 5,
    "REGULATION": 4,
    "SUPREME_COURT_PRECEDENT": 4,
    "JUDICIAL_DECISION": 3,
    "LEGAL_OPINION": 2,
    "CIRCULAR": 1,
    "SECONDARY_SOURCE": 0,
}

PRIMARY_TYPES = {"STATUTE", "REGULATION", "SUPREME_COURT_PRECEDENT"}


# V166.3: authority isolation. Retrieval candidates are only retained when the
# authority text/title shares a case-specific subject term with the issue or
# claim. Generic legal vocabulary is deliberately ignored.
_AUTHORITY_STOP = {
    "آیا", "است", "باشد", "شد", "شده", "شود", "می", "در", "به", "از", "با",
    "برای", "که", "این", "آن", "را", "و", "یا", "بر", "مورد", "موضوع",
    "پرونده", "مسئله", "ادعا", "ادعای", "اسناد", "سند", "قابل", "روشن",
    "بررسی", "مستند", "مستندات", "قانون", "قوانین", "ماده", "مواد",
}
_AUTHORITY_ALIASES = {
    "مهریه": {"مهریه", "مهر", "صداق"},
    "طلاق": {"طلاق", "زوجیت", "مطّلقه", "مطلقه", "گواهی عدم امکان سازش"},
    "نفقه": {"نفقه"},
    "اجرتالمثل": {"اجرتالمثل", "اجرت المثل", "اجرت‌المثل"},
    "اعسار": {"اعسار", "معسر", "تقسیط", "محکومبه", "محکوم‌به"},
    "تقسیط": {"تقسیط", "اعسار", "معسر", "محکومبه", "محکوم‌به"},
    "حضانت": {"حضانت", "ملاقات طفل", "حق ملاقات"},
    "تمکین": {"تمکین", "نشوز", "عدم تمکین"},
    "پرداخت": {"پرداخت", "واریز", "تأدیه", "عدم پرداخت"},
    "تجدیدنظرخواهی": {"تجدیدنظر", "تجدیدنظرخواهی", "واخواهی", "فرجام"},
    "ابلاغ": {"ابلاغ", "ابلاغیه", "مهلت", "موعد"},
    "صلاحیت": {"صلاحیت", "عدم صلاحیت", "مرجع رسیدگی", "سمت"},
    "خسارت": {"خسارت", "ضرر", "زیان", "وجه التزام", "غرامت"},
    "مالکیت": {"مالکیت", "مالک", "تصرف", "تصرف عدوانی", "خلع ید", "رهن", "وثیقه"},
    "فسخ/انحلال": {"فسخ", "انفساخ", "اقاله", "انحلال قرارداد"},
    "تحویل/تسلیم": {"تحویل", "تسلیم", "عدم تحویل", "عدم تسلیم"},
    "اجرا": {"اجرائیه", "اجرای حکم", "اجرای احکام", "مزایده", "توقیف"},
}

def _subject_terms(issue: Dict[str, Any], claim: Optional[Dict[str, Any]] = None) -> List[str]:
    claim=claim or {}
    raw=" ".join([_clean(issue.get("label")), _clean(issue.get("question")), _clean(claim.get("claim_text"))])
    normalized=_clean(raw).replace("‌", "").replace("ي", "ی").replace("ك", "ک")
    tokens=[x for x in re.findall(r"[آ-یA-Za-z]{3,}", normalized.lower()) if x not in _AUTHORITY_STOP]
    out=[]
    for token in tokens:
        out.extend(_AUTHORITY_ALIASES.get(token, {token}))
    # Also preserve multiword domain terms directly.
    for key, aliases in _AUTHORITY_ALIASES.items():
        if key in normalized.lower() or any(a in normalized for a in aliases):
            out.extend(aliases)
    return list(dict.fromkeys(x for x in out if len(x) >= 3))[:24]


def _authority_subject_overlap(record: Dict[str, Any], subject_terms: List[str]) -> List[str]:
    hay=_clean(" ".join([record.get("title") or "", record.get("law") or "", record.get("text") or "", record.get("clean_text") or "", record.get("topic") or ""]))
    hay=hay.replace("‌", "").replace("ي", "ی").replace("ك", "ک").lower()
    # Token-aware matching prevents short terms such as «مهر» or «مالک» from
    # matching unrelated longer words merely by substring coincidence.
    tokens=set(re.findall(r"[آ-یa-z]{2,}", hay))
    hits=[]
    for term in subject_terms:
        t=_clean(term).replace("‌", "").replace("ي", "ی").replace("ك", "ک").lower()
        if not t:
            continue
        compact=t.replace(" ", "")
        if " " in t or "‌" in term:
            if t in hay or term.replace("‌", " ").lower() in hay:
                hits.append(term)
        elif t in tokens or compact in tokens:
            hits.append(term)
    return list(dict.fromkeys(hits))




def _digits(v: Any) -> str:
    return _clean(v).translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))


def _authority_type(record: Dict[str, Any]) -> str:
    kind = str(record.get("kind") or "law")
    if kind == "ruling" and record.get("court_type") == "supreme_court":
        # The corpus currently contains general-assembly decisions; their
        # exact precedent effect is intentionally not inferred here.
        return "SUPREME_COURT_PRECEDENT"
    return AUTHORITY_TYPES.get(kind, "SECONDARY_SOURCE")


def _authority_status(record: Dict[str, Any]) -> str:
    """Normalize source metadata without turning local presence into validity."""
    s = _clean(record.get("source_status"))
    if s in {"verified", "verified_current", "verified_current_source_backed", "current_base_source_backed"}:
        return "ACTIVE"
    if s in {"repealed", "revoked"}:
        return "REPEALED"
    if s in {"superseded"}:
        return "SUPERSEDED"
    return "UNKNOWN"


def _parse_date(value: Any) -> Optional[date]:
    s = _digits(value)
    if not s:
        return None
    for parser in (parse_gregorian, parse_jalali):
        try:
            parsed = parser(s)
            if parsed:
                return parsed[-1] if isinstance(parsed, tuple) else parsed
        except Exception:
            pass
    # Common YYYY/MM/DD strings that the project parsers may reject.
    m = re.search(r"(1[234]\d{2})[/-](\d{1,2})[/-](\d{1,2})", s)
    if m:
        try:
            d = parse_jalali(f"{m.group(1)}/{m.group(2)}/{m.group(3)}")
            if d:
                return d
        except Exception:
            pass
    m = re.search(r"(19\d{2}|20\d{2})[/-](\d{1,2})[/-](\d{1,2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except Exception:
            return None
    return None


def _record_date(record: Dict[str, Any]) -> Optional[date]:
    return _parse_date(record.get("effective_from") or record.get("date") or record.get("source_date"))


def _event_dates(issue: Dict[str, Any]) -> List[date]:
    out = []
    for event in issue.get("related_events") or []:
        if not isinstance(event, dict):
            continue
        # V151 may expose a normalized date plus original date text. Prefer
        # the normalized value, but keep a conservative fallback.
        for key in ("date", "gregorian", "jalali", "original_text"):
            parsed = _parse_date(event.get(key))
            if parsed:
                out.append(parsed)
                break
    return sorted(set(out))


def temporal_applicability(record: Dict[str, Any], issue: Dict[str, Any]) -> Dict[str, Any]:
    """Conservative temporal signal. Unknown is a valid result."""
    events=_event_dates(issue)
    af=_parse_date(record.get("effective_from"))
    at=_parse_date(record.get("effective_to"))
    authority_date=_record_date(record)
    if af and events:
        first = min(events)
        if first < af:
            return {"status":"not_yet_effective_for_case_event", "warning":"دست‌کم یکی از وقایع مرتبط پرونده پیش از شروع اعتبار ثبت‌شده منبع است.", "case_event_date":first.isoformat()}
    if at and events:
        last = max(events)
        if last > at:
            return {"status":"expired_for_case_event", "warning":"دست‌کم یکی از وقایع مرتبط پرونده پس از پایان اعتبار ثبت‌شده منبع است.", "case_event_date":last.isoformat()}
    if authority_date and events:
        first=min(events)
        if authority_date > first:
            return {"status":"post_event_authority_date", "warning":"تاریخ منبع پس از یکی از وقایع مرتبط پرونده است؛ تقدم زمانی و اثر آن باید بررسی شود.", "authority_date":authority_date.isoformat(), "case_event_date":first.isoformat()}
        return {"status":"pre_or_same_event_date", "authority_date":authority_date.isoformat(), "case_event_date":first.isoformat()}
    if af or at:
        return {"status":"bounded_but_case_date_unknown"}
    return {"status":"unknown", "warning":"بازه اعتبار زمانی این منبع در corpus ثبت نشده است."}


def _source_verification(record: Dict[str, Any]) -> str:
    status=_clean(record.get("source_status"))
    if status in {"verified", "verified_current", "verified_current_source_backed", "current_base_source_backed"}:
        return "verified"
    return "review_required"


def normalize_authority(record: Dict[str, Any], *, issue_id: str = "", claim_id: str = "") -> Dict[str, Any]:
    """Turn an existing corpus record into the stable V154 authority shape."""
    record = dict(record or {})
    citation=record.get("citation") or {}
    kind=record.get("kind") or "law"
    title=_clean(record.get("title") or record.get("law"))
    locator=_clean(record.get("article") or record.get("ruling_number") or record.get("consultation_number"))
    authority_type=_authority_type(record)
    aid=str(citation.get("id") or f"AUTH-{kind}-{title}-{locator}")
    source_urls=list(record.get("source_urls") or citation.get("source_urls") or [])
    primary_sources=list(record.get("primary_sources") or citation.get("primary_sources") or [])
    return {
        "authority_id": aid,
        "authority_type": authority_type,
        "title": title,
        "issuer": _clean(record.get("law") or record.get("court") or record.get("مرجع")),
        "jurisdiction": "IR",
        "date": _clean(record.get("date") or "") or None,
        "effective_from": record.get("effective_from"),
        "effective_to": record.get("effective_to"),
        "status": _authority_status(record),
        "article_number": locator or None,
        "text": _clean(record.get("text") or record.get("clean_text")),
        "source_file": record.get("source_file"),
        "source_location": record.get("source_location") or locator or None,
        "citation_key": citation.get("id") or None,
        "source_status": record.get("source_status"),
        "verification_status": _source_verification(record),
        "verification_label": record.get("verification_label") or citation.get("verification_label"),
        "source_urls": source_urls,
        "primary_sources": primary_sources,
        "last_verified": record.get("last_verified") or citation.get("last_verified"),
        "issue_id": issue_id or None,
        "claim_id": claim_id or None,
    }


def _query_plan(issue: Dict[str, Any], claim: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    claim=claim or {}
    issue_q=_clean(issue.get("question"))
    claim_q=_clean(claim.get("claim_text"))
    label=_clean(issue.get("label"))
    queries=[]
    for purpose,q in (("issue",issue_q),("claim",claim_q),("label",label)):
        if len(q) < 3: continue
        if q not in [x["query"] for x in queries]:
            queries.append({"purpose":purpose,"query":q})
    return queries[:3]


def build_query_plan(issue: Dict[str, Any], claim: Optional[Dict[str, Any]]=None) -> List[str]:
    return [x["query"] for x in _query_plan(issue, claim)]


def _rerank(candidates: Iterable[Dict[str, Any]], issue: Dict[str, Any], claim: Dict[str, Any], limit: int=8) -> List[Dict[str, Any]]:
    by={}
    subject_terms=_subject_terms(issue,claim)
    # V167.3: when a concrete claim exists, an authority must overlap with the
    # claim itself as well as the issue. This prevents a broad family/payment
    # issue from pulling in an unrelated source merely because both share a
    # generic domain word.
    claim_text=_clean(claim.get('claim_text'))
    claim_only_terms=_subject_terms({'label':'','question':''},{'claim_text':claim_text}) if claim_text else []
    issue_only_terms=_subject_terms(issue,{})
    for raw in candidates:
        rec=dict(raw)
        overlap=_authority_subject_overlap(rec,subject_terms)
        issue_overlap=_authority_subject_overlap(rec,issue_only_terms)
        claim_overlap=_authority_subject_overlap(rec,claim_only_terms) if claim_only_terms else []
        # V166.3 hard gate plus V167.3 claim-specific isolation.
        if not overlap or not issue_overlap:
            continue
        if claim_text and len(claim_only_terms) >= 2 and not claim_overlap:
            continue
        auth=normalize_authority(rec, issue_id=str(issue.get("issue_id") or ""), claim_id=str(claim.get("claim_id") or ""))
        key=auth["authority_id"]
        score=float(rec.get("retrieval_score") or 0)
        score += TYPE_PRIORITY.get(auth["authority_type"],0)*0.7
        if auth["verification_status"] == "verified": score += 1.5
        if auth["status"] == "UNKNOWN": score -= 0.2
        score += min(2.0, 0.75*len(overlap))
        auth["retrieval_score"]=round(score,3)
        auth["matched_terms"]=list(rec.get("matched_terms") or [])
        auth["subject_terms"]=subject_terms
        auth["subject_overlap"]=overlap
        auth["issue_subject_overlap"]=issue_overlap
        auth["claim_subject_overlap"]=claim_overlap
        auth["relation_reason"]="claim_and_issue_subject_overlap" if claim_text and claim_overlap else "issue_subject_overlap"
        by[key]=auth if key not in by or score > by[key]["retrieval_score"] else by[key]
    out=sorted(by.values(), key=lambda x:(-x["retrieval_score"], -TYPE_PRIORITY.get(x["authority_type"],0), x["authority_id"]))
    return out[:max(1,min(int(limit or 8),12))]


def build_authorities_for_issue(issue: Dict[str, Any], claim: Optional[Dict[str, Any]]=None, limit: int=8) -> Dict[str, Any]:
    claim=claim or {}
    candidates=[]
    queries=_query_plan(issue,claim)
    for q in queries:
        try:
            candidates.extend(search_legal_research(q["query"], limit=max(6,limit)))
        except Exception:
            continue
    authorities=_rerank(candidates,issue,claim,limit)
    links=[]; warnings=[]
    if candidates and not authorities:
        warnings.append({
            "type":"authority_subject_mismatch",
            "authority_id":None,
            "message":"منابع بازیابی‌شده با موضوع مشخص این مسئله/ادعا هم‌پوشانی کافی نداشتند و برای جلوگیری از استناد نامرتبط حذف شدند.",
        })
    for auth in authorities:
        temporal=temporal_applicability(auth,issue)
        auth["temporal_status"]=temporal.get("status")
        auth["temporal_warning"]=temporal.get("warning")
        links.append({
            "authority_id":auth["authority_id"],
            "claim_id":claim.get("claim_id"),
            "issue_id":issue.get("issue_id"),
            # Retrieval relevance is not legal support. The link remains a
            # candidate relation until a lawyer verifies applicability.
            "relation":"candidate_authority",
            "verification_status":auth["verification_status"],
            "temporal_status":auth["temporal_status"],
        })
        if auth.get("verification_status") != "verified":
            warnings.append({"type":"source_verification","authority_id":auth["authority_id"],"message":"وضعیت تطبیق منبع برای استناد نهایی کافی نیست و نیازمند بازبینی است."})
        if auth.get("temporal_status") in {"unknown","bounded_but_case_date_unknown","post_event_authority_date"}:
            warnings.append({"type":"temporal","authority_id":auth["authority_id"],"message":auth.get("temporal_warning") or "اعتبار زمانی باید بررسی شود."})
    return {"query_plan":[x["query"] for x in queries],"authorities":authorities,"links":links,"warnings":warnings}


def build_case_authorities(uid: int, cid: int, *, per_claim: int=6) -> Dict[str, Any]:
    case=get_case(uid,int(cid))
    if not case:
        return {"version":154,"case_id":int(cid),"issues":[],"claims":[],"api_used":False,"error":"case_not_found"}
    issue_map=build_case_issues(uid,int(cid))
    evidence=build_evidence_matrix(uid,int(cid))
    claims_by_issue={}
    for claim in evidence.get("claims") or []:
        claims_by_issue.setdefault(str(claim.get("issue_id")),[]).append(claim)

    issues=[]; all_authorities=[]; all_links=[]; all_warnings=[]
    for issue in issue_map.get("issues") or []:
        iclaims=claims_by_issue.get(str(issue.get("issue_id")),[])
        # If V153 did not create a claim, still research the issue itself.
        targets=iclaims[:6] or [{"claim_id":None,"claim_text":issue.get("question") or ""}]
        issue_authorities=[]
        issue_queries=[]
        for claim in targets:
            result=build_authorities_for_issue(issue,claim,per_claim)
            issue_queries.extend(result["query_plan"])
            issue_authorities.extend(result["authorities"])
            all_links.extend(result["links"])
            all_warnings.extend(result["warnings"])
        dedup={x["authority_id"]:x for x in issue_authorities}
        selected=sorted(dedup.values(), key=lambda x:(-x["retrieval_score"],x["authority_id"]))[:max(1,per_claim*2)]
        # Keep a compact but explicit gap signal instead of pretending no hit means no law.
        primary=[x for x in selected if x["authority_type"] in PRIMARY_TYPES]
        missing_primary=not bool(primary)
        issue_out=dict(issue)
        issue_out["legal_authorities"]=[x["authority_id"] for x in selected]
        issue_out["authority_count"]=len(selected)
        issue_out["primary_authority_count"]=len(primary)
        issue_out["authority_gap"]=missing_primary
        issue_out["authority_review_required"]=any(x["verification_status"]!="verified" or x["temporal_status"]!="pre_or_same_event_date" for x in selected)
        issue_out["authority_query_plan"]=list(dict.fromkeys(issue_queries))[:8]
        issues.append(issue_out)
        all_authorities.extend(selected)

    # Deduplicate authority registry entries while preserving issue/claim links separately.
    registry={}
    for a in all_authorities:
        registry.setdefault(a["authority_id"],a)
    warnings=[]
    seenw=set()
    for w in all_warnings:
        k=(w.get("type"),w.get("authority_id"),w.get("message"))
        if k not in seenw:
            seenw.add(k); warnings.append(w)
    counts={
        "issues":len(issues),
        "claims":len(evidence.get("claims") or []),
        "authorities":len(registry),
        "primary_authorities":sum(a["authority_type"] in PRIMARY_TYPES for a in registry.values()),
        "verification_review":sum(a["verification_status"]!="verified" for a in registry.values()),
        "temporal_review":sum(a["temporal_status"] not in {"pre_or_same_event_date"} for a in registry.values()),
        "authority_gaps":sum(bool(i.get("authority_gap")) for i in issues),
    }
    return {
        "version":154,
        "case_id":int(cid),
        "case_name":_clean(case.get("file_name")),
        "issues":issues,
        "claims":evidence.get("claims") or [],
        "authorities":list(registry.values()),
        "links":all_links,
        "warnings":warnings,
        "counts":counts,
        "api_used":False,
        "resolver_path":["case_db","v152_issue_map","v153_evidence_matrix","issue_claim_query_plan","existing_local_legal_search","authority_normalization","source_verification","temporal_applicability","citation_links"],
        "legal_conclusion_generated":False,
        "strategy_generated":False,
    }


def format_case_authorities(result: Dict[str, Any], limit: int=8) -> str:
    r=result or {}; c=r.get("counts") or {}; issues=r.get("issues") or []; auth={x.get("authority_id"):x for x in r.get("authorities") or []}
    lines=["⚖️ نقشه مستندات قانونی پرونده","",f"مسائل: {c.get('issues',0)} | ادعاها: {c.get('claims',0)} | منابع: {c.get('authorities',0)} | منبع اصلی: {c.get('primary_authorities',0)}",f"⚠️ نیازمند بررسی منبع: {c.get('verification_review',0)} | هشدار زمانی: {c.get('temporal_review',0)} | خلأ منبع اصلی: {c.get('authority_gaps',0)}","", "این بخش منبع قانونی نامزد را پیدا و ردیابی می‌کند؛ نتیجه حقوقی یا تشخیص قطعی اعتبار قانون ارائه نمی‌کند."]
    for issue in issues[:max(1,limit)]:
        lines += ["",f"🎯 {issue.get('label','مسئله')} — {issue.get('category_label','عمومی')}",f"❓ {_clean(issue.get('question'))[:360]}"]
        ids=issue.get("legal_authorities") or []
        if not ids: lines.append("⚠️ برای این مسئله منبع قانونی نامزد پیدا نشد."); continue
        for aid in ids[:4]:
            a=auth.get(aid) or {}
            label=f"{a.get('title') or 'منبع'}"
            if a.get('article_number'): label += f" — {a['article_number']}"
            icon="🟢" if a.get('verification_status')=='verified' else "🟠"
            lines.append(f"{icon} {label} [{a.get('authority_type','—')}]")
            if a.get('temporal_warning'): lines.append(f"   ⏳ {a['temporal_warning']}")
    if r.get('warnings'):
        lines += ["", "⚠️ هشدارهای بازبینی:"]
        for w in r['warnings'][:5]: lines.append(f"• {w.get('message','')}")
    lines += ["", "🔒 مسیر: V152 → V153 → V154 | API خارجی: استفاده نشد"]
    return "\n".join(lines)
