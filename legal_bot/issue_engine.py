# -*- coding: utf-8 -*-
"""V152 — local-first legal issue map.

Turns V151 chronology + current case documents into a reviewable map of
candidate legal issues. It separates factual signals from legal questions and
never invents a legal rule, authority, conclusion, or missing fact.
"""
from __future__ import annotations

from .text_utils import clean_whitespace as _clean
from .text_utils import normalize_persian_text as _norm

import re
from typing import Any, Dict, List, Tuple

from .analysis import analyze
from .db import get_case, get_case_documents
from .timeline_engine import build_case_chronology
from .source_quality import source_segment_ok

ISSUE_CATEGORIES = {
    "procedural": ("آیین دادرسی/شکلی", r"دادخواست|ابلاغ|مهلت|تجدیدنظر|اعتراض|واخواهی|فرجام|جلسه|شعبه|صلاحیت|مرجع|سمت"),
    "contractual": ("قراردادی/تعهدات", r"قرارداد|عقد|تعهد|موجر|مستأجر|فروشنده|خریدار|الحاقیه|فسخ|انفساخ|اقاله|نقض|تخلف|عدم انجام"),
    "payment": ("مالی/پرداخت", r"پرداخت|واریز|ثمن|دین|وجه|چک|سفته|اقساط|سررسید|عدم پرداخت|مطالبه"),
    "damages": ("خسارت/وجه التزام", r"خسارت|ضرر|زیان|وجه التزام|خسارت تأخیر|اجرت المثل|غرامت"),
    "evidence": ("ادله/اثبات", r"سند|مدرک|رسید|اظهارنامه|شهادت|شاهد|کارشناس|کارشناسی|تأمین دلیل|اقرار|امضا|اصل سند|انکار|تردید|جعل"),
    "property": ("اموال/تصرف", r"مالکیت|تصرف|تحویل|تسلیم|ملک|مبیع|مورد معامله|تخلیه|ودیعه|رهن|وثیقه|توقیف"),
    "family": ("خانواده", r"مهریه|نفقه|طلاق|حضانت|ملاقات|اجرت المثل|تمکین|زوج|زوجه"),
    "enforcement": ("اجرا", r"اجرائیه|اجرای حکم|اجرای احکام|توقیف|مزایده|محکومیت|استرداد"),
}


QUESTION_CATEGORY = {
    "طلاق": "family",
    "مهریه": "family",
    "نفقه": "family",
    "اجرت‌المثل": "family",
    "اعسار/تقسیط": "enforcement",
    "حضانت/ملاقات": "family",
    "تمکین": "family",
    "پرداخت": "payment",
    "انجام تعهد": "contractual",
    "فسخ/انحلال": "contractual",
    "تحویل/تسلیم": "property",
    "ابلاغ/مهلت": "procedural",
    "مرجع/صلاحیت": "procedural",
    "ادله": "evidence",
    "خسارت": "damages",
    "مالکیت/تصرف": "property",
    "اجرا": "enforcement",
}

QUESTION_PATTERNS = [
    # V166.3: issue extraction is intentionally domain-gated. Generic legal
    # checklists are not issues by themselves; an issue must have an explicit
    # case signal in the source text.
    ("طلاق", "آیا موضوع طلاق و مبنای درخواست/دفاع درباره آن در اسناد پرونده روشن و قابل ردیابی است؟", r"طلاق|طلاقی|طلاق رجعی|طلاق بائن|گواهی عدم امکان سازش"),
    ("مهریه", "آیا ادعا، مطالبه یا وضعیت مهریه/مهر در اسناد پرونده روشن و قابل ردیابی است؟", r"مهریه|مهر|صداق"),
    ("نفقه", "آیا ادعا یا مطالبه نفقه و مستندات مربوط به آن در پرونده قابل ردیابی است؟", r"نفقه"),
    ("اجرت‌المثل", "آیا ادعا یا مطالبه اجرت‌المثل و مستندات مربوط به آن در پرونده قابل ردیابی است؟", r"اجرت[‌\s]*المثل"),
    ("اعسار/تقسیط", "آیا ادعای اعسار، تقسیط یا وضعیت مالی مرتبط با محکوم‌به در اسناد پرونده روشن است؟", r"اعسار|معسر|تقسیط|دادخواست اعسار"),
    ("حضانت/ملاقات", "آیا موضوع حضانت یا ملاقات و مبنای درخواست/دفاع درباره آن در اسناد پرونده روشن است؟", r"حضانت|ملاقات طفل|حق ملاقات"),
    ("تمکین", "آیا موضوع تمکین یا عدم تمکین و مستندات آن در پرونده به‌صراحت مطرح شده است؟", r"تمکین|عدم تمکین"),
    ("پرداخت", "آیا پرداخت/تأدیه ادعایی با اسناد پرونده قابل اثبات و با تاریخ و مبلغ آن منطبق است؟", r"پرداخت|واریز|تأدیه|عدم پرداخت|عدم\s+تأدیه"),
    ("انجام تعهد", "آیا تعهد مورد بحث انجام شده، ناقص انجام شده یا نقض آن به‌صراحت ادعا شده است؟", r"تعهد|ایفاء|انجام تعهد|عدم انجام|نقض تعهد|تخلف از تعهد"),
    ("فسخ/انحلال", "آیا مبنای فسخ، انفساخ یا خاتمه قرارداد و شرایط اعمال آن در اسناد پرونده روشن است؟", r"فسخ|انفساخ|اقاله|خاتمه قرارداد|انحلال قرارداد"),
    ("تحویل/تسلیم", "آیا تحویل یا تسلیم مورد معامله/تعهد و تاریخ آن با اسناد پرونده قابل احراز است؟", r"تحویل|تسلیم|عدم تحویل|عدم تسلیم"),
    ("ابلاغ/مهلت", "آیا تاریخ ابلاغ و مهلت مرتبط با اقدام یا اعتراض از اسناد موجود قابل احراز است؟", r"ابلاغ|ابلاغیه|مهلت|موعد|تجدیدنظرخواهی|واخواهی|فرجام[‌\s]*خواهی"),
    ("مرجع/صلاحیت", "آیا صلاحیت مرجع رسیدگی یا سمت مطرح‌شده در پرونده صراحتاً محل بحث است؟", r"عدم صلاحیت|ایراد صلاحیت|صلاحیت دادگاه|صلاحیت مرجع|ایراد عدم صلاحیت|سمت"),
    ("ادله", "آیا برای ادعای مورد بحث دلیل مستقیم و قابل ردیابی، یا اختلافی درباره دلیل، در اسناد پرونده وجود دارد؟", r"شهادت|شاهد|کارشناس|کارشناسی|تأمین دلیل|اقرار|انکار|تردید|جعل|اصالت سند|انکار امضا|تردید در سند"),
    ("خسارت", "آیا مبنای مطالبه خسارت یا وجه التزام، وقوع زیان/تخلف و مستندات آن در پرونده روشن است؟", r"خسارت|ضرر و زیان|وجه التزام|خسارت تأخیر|غرامت"),
    ("مالکیت/تصرف", "آیا وضعیت مالکیت، تصرف یا حق مورد ادعا با اسناد پرونده قابل ردیابی است؟", r"مالکیت|مالک|تصرف عدوانی|تصرف|خلع ید|تخلیه|رهن|وثیقه|توقیف ملک"),
    ("اجرا", "آیا اقدام اجرایی، اجرائیه یا وضعیت اجرای رأی در پرونده مستند و مشخص است؟", r"اجرائیه|اجرای حکم|اجرای احکام|مزایده|استرداد محکوم به|توقیف اموال") ,
]







def _sentences(text: str) -> List[Tuple[Any, Any, str]]:
    out=[]
    for page, body in _pages(text):
        chunks = re.split(r"(?<=[؟.!؛])\s+|[\r\n]+", body)
        for x in chunks:
            x=_clean(x).strip(" -•▪◦")
            if len(x)>=20 and source_segment_ok(x, min_chars=20):
                out.append((None, page, x[:900]))
    return out


def _pages(text: str):
    ms=list(re.finditer(r"\[صفحه\s+(\d+)\]", text or ""))
    if not ms: return [(None, text or "")]
    out=[]
    for i,m in enumerate(ms):
        end=ms[i+1].start() if i+1<len(ms) else len(text)
        body=text[m.end():end].strip()
        if body: out.append((int(m.group(1)), body))
    return out


def _category(text: str) -> str:
    hits=[]
    for key,(label,pat) in ISSUE_CATEGORIES.items():
        n=len(re.findall(pat,text,re.I))
        if n: hits.append((n,key))
    return max(hits)[1] if hits else "general"


def _category_label(key: str) -> str:
    return ISSUE_CATEGORIES.get(key,("عمومی", ""))[0]


def _sources_for(sentences: List[Tuple[Any,Any,str]], pattern: str, limit: int=6) -> List[Dict[str,Any]]:
    out=[]; seen=set()
    for document_id,page,text in sentences:
        if not re.search(pattern,text,re.I): continue
        key=(document_id,page,text)
        if key in seen: continue
        seen.add(key)
        stance = "party_assertion" if re.search(r"مدعی|ادعا|به ادعای|حسب اظهارات|اظهارات", text) else "source_signal"
        out.append({"document_id":document_id,"page":page,"text":text[:900],"stance":stance})
        if len(out)>=limit: break
    return out


def _contrary_sources(sentences: List[Tuple[Any,Any,str]], pattern: str, limit: int=5) -> List[Dict[str,Any]]:
    """Find source sentences that carry a contrary/denial signal.

    This is a review signal, not a credibility finding: the engine only marks
    explicit lexical opposition such as «انکار»، «عدم»، «نشد» or «ولی».
    """
    neg = r"انکار|منکر|عدم\s+(?:پرداخت|انجام|تحویل|ابلاغ)|نشد(?:ه)?|نکرد(?:ه)?|رد\s+(?:شد|می‌کند|کرد)|مخالف|در حالی که|با وجود"
    out=[]; seen=set()
    for document_id,page,text in sentences:
        if not re.search(pattern,text,re.I) or not re.search(neg,text,re.I): continue
        key=(document_id,page,text)
        if key in seen: continue
        seen.add(key); out.append({"document_id":document_id,"page":page,"text":text[:900],"stance":"contrary_signal"})
        if len(out)>=limit: break
    return out


def _event_signals(chronology: Dict[str,Any], pattern: str, limit: int=6) -> List[Dict[str,Any]]:
    out=[]
    for e in chronology.get("events") or []:
        hay=_clean(" ".join([e.get("title", ""),e.get("description","")]))
        if re.search(pattern,hay,re.I):
            src=(e.get("sources") or [{}])[0]
            out.append({"event_id":e.get("event_id"),"date":(e.get("date") or {}).get("jalali_date"),"status":e.get("status"),"title":e.get("title"),"source":{"document_id":src.get("document_id"),"document_name":src.get("document_name"),"page":src.get("page")}})
            if len(out)>=limit: break
    return out


def _signal_quality(text: str) -> bool:
    """Reject obvious OCR/header/footer fragments before issue extraction."""
    t=_clean(text)
    if len(t) < 24:
        return False
    if re.search(r"این مجموعه برای آموزش|تمرین کارآموزان|پرونده آموزشی", t):
        return False
    # A fragment made almost entirely of labels/numbers is not a legal issue.
    alpha=len(re.findall(r"[آ-یA-Za-z]", t))
    digits=len(re.findall(r"[0-9۰-۹]", t))
    if alpha < 10 or digits > max(12, alpha*2):
        return False
    return True


def _candidate_questions(sentences: List[Tuple[Any,str]], chronology: Dict[str,Any]) -> List[Dict[str,Any]]:
    out=[]
    for label,question,pattern in QUESTION_PATTERNS:
        src=[x for x in _sources_for(sentences,pattern,8) if _signal_quality(x.get("text", ""))]
        contrary=[x for x in _contrary_sources(sentences,pattern,8) if _signal_quality(x.get("text", ""))]
        events=_event_signals(chronology,pattern,6)
        if not src and not events:
            continue
        support=sum(1 for x in src if x.get("text")) + len(events)
        uncertainty=bool(contrary) or any(x.get("status") in {"conflict","uncertain","party_assertion","undated"} for x in events)
        out.append({"key":label,"question":question,"signals":src,"contrary":contrary,"events":events,"support_count":support,"needs_review":bool(uncertainty)})
    return out


def _unmapped(sentences: List[Tuple[Any,Any,str]], issues: List[Dict[str,Any]]) -> List[Dict[str,Any]]:
    covered=set()
    for issue in issues:
        for s in issue.get("signals") or []: covered.add((s.get("page"),s.get("text")))
    out=[]
    for document_id,page,text in sentences:
        if (page,text) in covered: continue
        if any(k in text for k in ("خواهان","خوانده","ادعا","دفاع","درخواست","مطالبه","قرارداد","تعهد","رأی","دادنامه","پرداخت","ابلاغ")):
            out.append({"document_id":document_id,"page":page,"text":text})
        if len(out)>=12: break
    return out


def build_case_issues(uid: int, cid: int) -> Dict[str,Any]:
    case=get_case(uid,int(cid))
    if not case:
        return {"version":152,"case_id":int(cid),"issues":[],"api_used":False,"error":"case_not_found"}
    chronology=build_case_chronology(uid,int(cid),include_undated=True)
    docs=get_case_documents(uid,int(cid))
    sentences=[]
    doc_count=0
    for doc in docs:
        text=_clean(doc.get("extracted_text"))
        if not text: continue
        doc_count+=1
        for _, page, s in _sentences(text):
            sentences.append((doc.get("id"), page, s))
    questions=_candidate_questions(sentences,chronology)
    issues=[]
    for idx,q in enumerate(questions,1):
        category=QUESTION_CATEGORY.get(q["key"], _category(" ".join(x.get("text","") for x in q.get("signals",[]))))
        issue={
            "issue_id":f"iss-{idx:04d}",
            "question":q["question"],
            "label":q["key"],
            "category":category,
            "category_label":_category_label(category),
            "status":"needs_review" if q["needs_review"] else "candidate",
            "supporting_signals":q["signals"],
            "related_events":q["events"],
            "contrary_signals":q.get("contrary",[]),
            "missing_information":[],
            "legal_authorities":[],
            "confidence":round(min(0.95,0.45+0.08*q["support_count"]),3),
            "lawyer_decision":None,
        }
        if q["needs_review"]: issue["missing_information"].append("برخی وقایع مرتبط دارای تعارض، ابهام، ادعا یا تاریخ نامشخص‌اند.")
        if q.get("contrary"): issue["missing_information"].append("برای این مسئله نشانه مخالف/انکاری نیز در متن پیدا شد؛ هر دو طرف باید با اصل سند بررسی شوند.")
        if not q["signals"]: issue["missing_information"].append("نشانه متنی مستقیم برای این مسئله کافی نیست.")
        issues.append(issue)
    # Preserve only legally/procedurally salient chronology conflicts as
    # standalone review issues.  Conflicting ordinary factual dates (for
    # example marriage/payment dates) belong in the timeline, not as a generic
    # «آیین دادرسی» issue.
    procedural_conflict_types={"filing","service","hearing","judgment","appeal","execution"}
    for conflict in chronology.get("conflicts") or []:
        if conflict.get("event_type") not in procedural_conflict_types:
            continue
        issues.append({
            "issue_id":f"iss-{len(issues)+1:04d}",
            "question":"کدام تاریخ/روایت درباره این واقعه باید بر اساس اصل اسناد تأیید شود؟",
            "label":"تعارض زمانی",
            "category":"procedural",
            "category_label":"آیین دادرسی/شکلی",
            "status":"conflict",
            "supporting_signals":[],
            "related_events":[{"event_ids":conflict.get("event_ids"),"dates":conflict.get("dates"),"event_type":conflict.get("event_type")}],
            "contrary_signals":[],
            "missing_information":["اصل اسناد و محل دقیق تاریخ‌های متعارض باید بررسی شود."],
            "legal_authorities":[],
            "confidence":0.98,
            "lawyer_decision":None,
        })
    unmapped=_unmapped(sentences,issues)
    counts={"issues":len(issues),"candidate":sum(x.get("status")=="candidate" for x in issues),"needs_review":sum(x.get("status")=="needs_review" for x in issues),"conflict":sum(x.get("status")=="conflict" for x in issues),"unmapped":len(unmapped)}
    return {
        "version":152,"case_id":int(cid),"case_name":_clean(case.get("file_name")),"issues":issues,
        "unmapped_facts":unmapped,"chronology_counts":chronology.get("counts",{}),"counts":counts,
        "source_documents":doc_count,"api_used":False,
        "resolver_path":["case_db","current_case_documents","v151_chronology","issue_signal_extraction","issue_question_mapping","conflict_propagation","unmapped_fact_preservation"],
        "legal_conclusion_generated":False,"legal_authorities_generated":False,
    }


def format_case_issues(result: Dict[str,Any], limit: int=10) -> str:
    r=result or {}; issues=r.get("issues") or []; counts=r.get("counts") or {}
    lines=["🎯 نقشه مسائل حقوقی پرونده","",f"مسائل: {counts.get('issues',0)} | نیازمند بازبینی: {counts.get('needs_review',0)} | تعارض: {counts.get('conflict',0)} | موارد بدون نقشه: {counts.get('unmapped',0)}","", "⚠️ این بخش «مسئله قابل بررسی» را استخراج می‌کند؛ حکم حقوقی یا ماده قانون صادر نمی‌کند."]
    for i in issues[:max(1,limit)]:
        icon="🟠" if i.get("status") in {"needs_review","conflict"} else "🟡"
        lines += ["",f"{icon} {i.get('label','مسئله')} — {i.get('category_label','عمومی')}",f"❓ {i.get('question','')}"]
        sig=i.get("supporting_signals") or []
        if sig:
            s=sig[0]; lines.append(f"📄 {_clean(s.get('text'))[:300]}" + (f" — ص.{s.get('page')}" if s.get('page') else ""))
        contrary=i.get("contrary_signals") or []
        if contrary:
            lines.append(f"↔️ نشانه مخالف: {_clean(contrary[0].get('text'))[:260]}")
        miss=i.get("missing_information") or []
        for m in miss[:2]: lines.append(f"⚠️ {m}")
    if len(issues)>limit: lines.append(f"\n… {len(issues)-limit} مسئله دیگر")
    if r.get("unmapped_facts"):
        lines += ["", "🧩 واقعیت‌های مهمی که فعلاً به مسئله‌ای نگاشت نشدند:"]
        for x in r["unmapped_facts"][:4]: lines.append(f"• {_clean(x.get('text'))[:300]}")
    lines += ["", "🔗 منبع اصلی: وقایع V151 و اسناد جاری پرونده | API خارجی: استفاده نشد"]
    return "\n".join(lines)
