# -*- coding: utf-8 -*-
"""V151 — local-first legal case chronology / temporal engine.

Builds a source-linked chronology from current case documents. It deliberately
keeps legal-event dates separate from document/Telegram timestamps and never
turns an ambiguous date into a precise fact.
"""
from __future__ import annotations

from .text_utils import clean_whitespace as _clean

import re
from collections import defaultdict
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from .source_quality import source_segment_ok, is_probable_source_noise
from .calendar_dates import (
    MONTHS, extract_important_dates, gregorian_to_jalali, normalize_digits,
    parse_gregorian, parse_jalali,
)
from .db import get_case, get_case_documents, get_case_versions, get_case_text

STATUS_VERIFIED = "verified"
STATUS_ASSERTION = "party_assertion"
STATUS_UNCERTAIN = "uncertain"
STATUS_CONFLICT = "conflict"
STATUS_INFERRED = "inferred"
STATUS_UNDATED = "undated"

PRECISION_EXACT = "exact"
PRECISION_APPROXIMATE = "approximate"
PRECISION_YEAR = "year"
PRECISION_MONTH = "month"
PRECISION_RANGE = "range"

EVENT_TYPES = {
    "filing": ("LEGAL", re.compile(r"دادخواست|ثبت\s+دادخواست|طرح\s+دعوا", re.I)),
    "service": ("LEGAL", re.compile(r"ابلاغ|تاریخ\s+ابلاغ", re.I)),
    "hearing": ("LEGAL", re.compile(r"جلسه\s+(?:رسیدگی|دادگاه|دادرسی)|وقت\s+رسیدگی", re.I)),
    "judgment": ("LEGAL", re.compile(r"رأی|رای|حکم|دادنامه|صدور\s+رأی|صدور\s+حکم", re.I)),
    "appeal": ("LEGAL", re.compile(r"تجدیدنظر|اعتراض|واخواهی|فرجام", re.I)),
    "execution": ("LEGAL", re.compile(r"اجرائیه|اجرای\s+حکم|اجرای\s+دادنامه|توقیف", re.I)),
    "contract": ("CONTRACT", re.compile(r"قرارداد|عقد|انعقاد|تنظیم\s+قرارداد", re.I)),
    "amendment": ("CONTRACT", re.compile(r"الحاقیه|اصلاح\s+قرارداد|تعدیل\s+قرارداد", re.I)),
    "breach": ("CONTRACT", re.compile(r"نقض\s+تعهد|تخلف|عدم\s+انجام\s+تعهد|ایفاء\s+نشد", re.I)),
    "termination": ("CONTRACT", re.compile(r"فسخ|اقاله|خاتمه|انحلال", re.I)),
    "payment": ("FINANCIAL", re.compile(r"پرداخت|واریز|تأدیه|تادیه|وجه|ثمن|قسط|اقساط|چک|سفته", re.I)),
    "delivery": ("FACTUAL", re.compile(r"تحویل|تسلیم|دریافت\s+کالا|تحویل\s+مورد", re.I)),
    "notice": ("COMMUNICATION", re.compile(r"اظهارنامه|اخطار|نامه|مکاتبه|پیام|ایمیل", re.I)),
    "inspection": ("FACTUAL", re.compile(r"کارشناس|بازدید|معاینه|تأمین\s+دلیل|تامین\s+دلیل", re.I)),
}

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")




def _norm(v: Any) -> str:
    s = normalize_digits(_clean(v)).replace("ي", "ی").replace("ك", "ک")
    return re.sub(r"[^\wآ-ی]+", " ", s.lower()).strip()


def _token_set(v: Any) -> set:
    return {x for x in _norm(v).split() if len(x) > 1}


def _similarity(a: Any, b: Any) -> float:
    aa, bb = _token_set(a), _token_set(b)
    if not aa or not bb:
        return 0.0
    return len(aa & bb) / max(1, len(aa | bb))


def _pages(text: str) -> List[Tuple[Optional[int], str]]:
    ms = list(re.finditer(r"\[صفحه\s+(\d+)\]", text or ""))
    if not ms:
        return [(None, text or "")]
    out: List[Tuple[Optional[int], str]] = []
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(text)
        body = text[m.end():end].strip()
        if body:
            out.append((int(m.group(1)), body))
    return out


def _sentence_for_match(body: str, start: int, end: int) -> str:
    left = max(body.rfind("\n", 0, start), body.rfind("؟", 0, start), body.rfind(".", 0, start), body.rfind("؛", 0, start))
    rights = [x for x in (body.find("\n", end), body.find("؟", end), body.find(".", end), body.find("؛", end)) if x >= 0]
    right = min(rights) if rights else len(body)
    sentence = _clean(body[left + 1:right])
    # A legal sentence can contain several independent dated actions joined
    # with «و». Keep the clause containing this date so event classification is
    # tied to the date's local action instead of the whole sentence.
    clauses = [c.strip() for c in re.split(r"\s+و\s+", sentence) if c.strip()]
    if len(clauses) > 1:
        pos = sentence.find(body[start:end])
        cursor = 0
        for clause in clauses:
            idx = sentence.find(clause, cursor)
            if idx <= pos < idx + len(clause):
                return _clean(clause)[:900]
            cursor = idx + len(clause)
    return sentence[:900]


def _date_context_kind(context: str) -> str:
    s = _clean(context)
    if re.search(r"(?:تاریخ|روز|در|مورخ)\s+(?:سند|مدرک|تنظیم|صدور|انعقاد)", s):
        return "document_or_instrument"
    if re.search(r"(?:مدعی|ادعا|به ادعای|از نظر|حسب اظهارات|اظهارات|اظهار(?!نامه))", s):
        return STATUS_ASSERTION
    return STATUS_VERIFIED


def _event_type(context: str) -> Tuple[str, str]:
    matches = []
    for key, (group, pat) in EVENT_TYPES.items():
        if pat.search(context):
            matches.append((key, group))
    # More specific legal actions should win over broad communication/payment labels.
    priority = ["judgment", "hearing", "service", "filing", "appeal", "execution", "termination", "breach", "payment", "delivery", "contract", "amendment", "notice", "inspection"]
    for key in priority:
        for k, group in matches:
            if k == key:
                return k, group
    return "other", "FACTUAL"


def _event_title(event_type: str, context: str) -> str:
    labels = {
        "filing": "ثبت/طرح دعوا",
        "service": "ابلاغ",
        "hearing": "جلسه رسیدگی",
        "judgment": "رأی/حکم",
        "appeal": "اعتراض/تجدیدنظر",
        "execution": "اجرای حکم/اقدام اجرایی",
        "contract": "انعقاد/تنظیم قرارداد",
        "amendment": "اصلاح/الحاق قرارداد",
        "breach": "نقض/عدم انجام تعهد",
        "termination": "فسخ/خاتمه قرارداد",
        "payment": "پرداخت/تأدیه",
        "delivery": "تحویل/تسلیم",
        "notice": "اظهارنامه/مکاتبه",
        "inspection": "کارشناسی/بازدید/تأمین دلیل",
        "other": "رویداد پرونده",
    }
    return labels.get(event_type, "رویداد پرونده")


def _approximate_date(raw: str) -> Dict[str, Any]:
    s = _clean(raw)
    norm = normalize_digits(s)
    # Exact Jalali/Gregorian first.
    parsed = parse_jalali(norm)
    if parsed:
        y, m, d, g = parsed
        return {
            "original_text": s, "calendar": "jalali", "jalali_date": f"{y:04d}/{m:02d}/{d:02d}",
            "gregorian_date": g.isoformat(), "precision": PRECISION_EXACT,
            "range_start": g.isoformat(), "range_end": g.isoformat(), "is_inferred": False,
        }
    parsed = parse_gregorian(norm)
    if parsed:
        y, m, d, g = parsed
        jy, jm, jd = gregorian_to_jalali(g)
        return {
            "original_text": s, "calendar": "gregorian", "jalali_date": f"{jy:04d}/{jm:02d}/{jd:02d}",
            "gregorian_date": g.isoformat(), "precision": PRECISION_EXACT,
            "range_start": g.isoformat(), "range_end": g.isoformat(), "is_inferred": False,
        }
    # Persian approximate month expressions.
    month_match = re.search(r"(اوایل|ابتدای|اواسط|نیمه|اواخر|پایان)?\s*(فروردین|اردیبهشت|خرداد|تیر|مرداد|شهریور|مهر|آبان|آذر|دی|بهمن|اسفند)\s*([0-9]{4})", norm)
    if month_match:
        qualifier, month_name, year_s = month_match.groups()
        month = MONTHS[month_name]; year = int(year_s)
        starts = {None: 1, "اوایل": 1, "ابتدای": 1, "اواسط": 11, "نیمه": 11, "اواخر": 21, "پایان": 21}
        start_day = starts.get(qualifier, 1)
        end_day = 10 if start_day == 1 and qualifier else (20 if start_day == 11 else 31)
        if month <= 6:
            month_len = 31
        elif month <= 11:
            month_len = 30
        else:
            # Conservative leap-year handling: conversion itself validates the day.
            month_len = 30
        end_day = min(end_day, month_len)
        start_g = jalali_to_gregorian_safe(year, month, start_day)
        end_g = jalali_to_gregorian_safe(year, month, end_day)
        return {
            "original_text": s, "calendar": "jalali", "jalali_date": f"{year:04d}/{month:02d}",
            "gregorian_date": start_g.isoformat(), "precision": PRECISION_RANGE,
            "range_start": start_g.isoformat(), "range_end": end_g.isoformat(), "is_inferred": False,
        }
    return {
        "original_text": s, "calendar": "unknown", "jalali_date": None, "gregorian_date": None,
        "precision": PRECISION_APPROXIMATE, "range_start": None, "range_end": None, "is_inferred": False,
    }


def jalali_to_gregorian_safe(y: int, m: int, d: int) -> date:
    from .calendar_dates import jalali_to_gregorian
    # Clamp invalid approximate end dates conservatively.
    for candidate in range(d, 0, -1):
        try:
            return jalali_to_gregorian(y, m, candidate)
        except Exception:
            continue
    raise ValueError("invalid Jalali date")


def _source(meta: Dict[str, Any], page: Optional[int], snippet: str, raw_date: str, start: Optional[int] = None, end: Optional[int] = None) -> Dict[str, Any]:
    return {
        "type": "case_document",
        "document_id": meta.get("id"),
        "document_name": meta.get("file_name") or f"سند #{meta.get('id', '?')}",
        "page": page,
        "snippet": _clean(snippet)[:1000],
        "original_date_text": raw_date,
        "char_start": start,
        "char_end": end,
    }


def _actors(context: str, parties: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    # Prefer explicit legal roles in the local event sentence. This prevents a
    # broad party extractor from swallowing the rest of the sentence into a
    # person's name when OCR punctuation is weak.
    for role in ("خواهان", "خوانده", "موکل", "وکیل", "موجر", "مستأجر", "شاکی", "مشتکی عنه"):
        if re.search(rf"(?<![آ-ی]){re.escape(role)}(?![آ-ی])", context):
            out.append({"name": role, "role": role})
    if out:
        return out[:8]
    for p in parties or []:
        name = _clean(p.get("name")); role = _clean(p.get("role"))
        if name and name in context:
            out.append({"name": name, "role": role})
    return out[:8]


def _date_candidates(text: str) -> List[Tuple[str, Optional[int], str, int, int]]:
    """Return (raw, page, context, start, end) for date expressions."""
    out=[]; seen=set()
    for page, body in _pages(text):
        patterns=[
            re.compile(r'(?<!\d)([۰-۹0-9]{4}[/-][۰-۹0-9]{1,2}[/-][۰-۹0-9]{1,2})(?!\d)'),
            re.compile(r'(?<!\d)([۰-۹0-9]{4}[.-][۰-۹0-9]{1,2}[.-][۰-۹0-9]{1,2})(?!\d)'),
            re.compile(r'(?<!\d)((?:اوایل|ابتدای|اواسط|نیمه|اواخر|پایان)?\s*(?:فروردین|اردیبهشت|خرداد|تیر|مرداد|شهریور|مهر|آبان|آذر|دی|بهمن|اسفند)\s*[۰-۹0-9]{4})(?!\d)'),
        ]
        for pat in patterns:
            for m in pat.finditer(body):
                raw=_clean(m.group(1)); key=(page,_norm(raw))
                if key in seen: continue
                seen.add(key)
                out.append((raw,page,_sentence_for_match(body,m.start(),m.end()),m.start(),m.end()))
    return out

def _extract_doc_events(meta: Dict[str, Any], text: str) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    # Party-name enrichment used to call the heavyweight general analyzer for
    # every document.  Timeline extraction is deterministic/date-centric; the
    # general analyzer added latency without changing the legal-event result.
    # Keep actor extraction local and conservative instead.
    parties = []
    # Extract exact and approximate dates locally. We intentionally do not rely
    # on Telegram timestamps or document upload timestamps for legal event dates.
    for raw, page, context, start, end in _date_candidates(text):
        if not source_segment_ok(context, min_chars=18):
            continue
        date_info = _approximate_date(raw)
        date_role = "document_date" if re.search(r"(?:تاریخ|مورخ)\s+(?:سند|مدرک|تنظیم|صدور)", context) else "event_date"
        date_info["role"] = date_role
        etype, group = _event_type(context)
        status = _date_context_kind(context)
        title = _event_title(etype, context)
        if status == "document_or_instrument":
            status = STATUS_VERIFIED
        event = {
            "event_id": None,
            "date": date_info,
            "event_type": etype,
            "event_group": group,
            "title": title,
            "description": context or title,
            "actors": _actors(context, parties),
            "sources": [_source(meta, page, context, raw, start, end)],
            "status": status,
            "confidence": 0.88 if status == STATUS_VERIFIED else 0.62,
            "is_inferred": False,
            "temporal_relations": [],
            "review": {"reviewed": False, "reviewed_by": None},
            "lineage": {"source_document_id": meta.get("id"), "analysis_version": "V151"},
        }
        events.append(event)
    # Keep important undated legal events visible when a document contains a
    # strong event phrase but no parseable date. Do not invent a date.
    for page, body in _pages(text):
        for line in re.split(r"[\r\n]+", body):
            line = _clean(line)
            if len(line) < 25 or not source_segment_ok(line, min_chars=25):
                continue
            etype, group = _event_type(line)
            if etype == "other":
                continue
            if re.search(r"(?:تاریخ|مورخ|در\s+روز)\s*[0-9۰-۹]{1,4}", line) or re.search(r"[0-9۰-۹]{4}[/-][0-9۰-۹]{1,2}[/-][0-9۰-۹]{1,2}", line):
                continue
            if len(events) >= 120:
                break
            events.append({
                "event_id": None,
                "date": {"original_text": None, "calendar": "unknown", "jalali_date": None, "gregorian_date": None,
                          "precision": PRECISION_APPROXIMATE, "range_start": None, "range_end": None, "is_inferred": False},
                "event_type": etype, "event_group": group, "title": _event_title(etype, line),
                "description": line[:900], "actors": _actors(line, parties),
                "sources": [_source(meta, page, line, "")], "status": STATUS_UNDATED,
                "confidence": 0.55, "is_inferred": False, "temporal_relations": [],
                "review": {"reviewed": False, "reviewed_by": None},
                "lineage": {"source_document_id": meta.get("id"), "analysis_version": "V151"},
            })
    return events[:140]


def _signature(event: Dict[str, Any]) -> Tuple[Any, ...]:
    d = event.get("date") or {}
    actors = tuple(sorted(_norm(a.get("name")) for a in event.get("actors", []) if a.get("name")))
    # Keep party assertions separate from verified facts: merging them would
    # erase an important evidentiary distinction.
    status_class = STATUS_ASSERTION if event.get("status") == STATUS_ASSERTION else "fact"
    return (event.get("event_type"), d.get("gregorian_date"), d.get("range_start"), actors, status_class)


def _merge_duplicates(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    for e in events:
        key = _signature(e)
        base = groups.get(key)
        if base is None:
            groups[key] = e
            continue
        # Exact/near-identical descriptions from separate records are one event.
        # Keep a second row when wording is materially different so we don't
        # hide competing factual accounts.
        sim = _similarity(base.get("description"), e.get("description"))
        if sim < 0.70:
            alt_key = key + (len(groups),)
            groups[alt_key] = e
            continue
        base["sources"] = _merge_sources(base.get("sources", []), e.get("sources", []))
        base["actors"] = _merge_actor_lists(base.get("actors", []), e.get("actors", []))
        base["confidence"] = max(float(base.get("confidence", 0)), float(e.get("confidence", 0)))
        if base.get("status") == STATUS_UNCERTAIN and e.get("status") == STATUS_VERIFIED:
            base["status"] = STATUS_VERIFIED
    return list(groups.values())

def _merge_sources(a: List[Dict[str, Any]], b: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    seen = set()
    for src in list(a or []) + list(b or []):
        key = (src.get("document_id"), src.get("page"), _norm(src.get("snippet")))
        if key in seen:
            continue
        seen.add(key); out.append(src)
    return out[:12]


def _merge_actor_lists(a: List[Dict[str, Any]], b: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out=[]; seen=set()
    for x in list(a or []) + list(b or []):
        key=(_norm(x.get("name")), _norm(x.get("role")))
        if key in seen: continue
        seen.add(key); out.append(x)
    return out[:8]


def _detect_date_conflicts(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # Same event type + actor + highly similar wording but different exact dates.
    buckets: Dict[Tuple[Any, ...], List[Dict[str, Any]]] = defaultdict(list)
    for e in events:
        d = e.get("date") or {}
        if not d.get("gregorian_date") or e.get("status") == STATUS_UNDATED:
            continue
        actors = tuple(sorted(_norm(a.get("name")) for a in e.get("actors", []) if a.get("name")))
        words = set(_norm(e.get("description")).split()[:18])
        buckets[(e.get("event_type"), actors)].append((e, words))
    conflicts=[]
    for key, rows in buckets.items():
        dates={r[0]["date"].get("gregorian_date") for r in rows}
        if len(dates) <= 1 or len(rows) < 2:
            continue
        # Require textual overlap before declaring a date conflict.
        for i in range(len(rows)):
            for j in range(i+1,len(rows)):
                overlap=len(rows[i][1] & rows[j][1])
                if overlap >= 3:
                    for e in (rows[i][0], rows[j][0]):
                        e["status"] = STATUS_CONFLICT
                        e["notes"] = list(e.get("notes") or [])
                        e["notes"].append("برای یک رویداد مشابه بیش از یک تاریخ صریح در منابع دیده شد.")
                    pair = (rows[i][0], rows[j][0])
                    conflict_sources = []
                    for event in pair:
                        date_info = event.get("date") or {}
                        for source in event.get("sources") or []:
                            conflict_sources.append({
                                "event_id": event.get("event_id"),
                                "date": date_info.get("jalali_date") or date_info.get("gregorian_date") or date_info.get("original_text"),
                                "document_id": source.get("document_id"),
                                "document_name": source.get("document_name"),
                                "page": source.get("page"),
                                "snippet": _clean(source.get("snippet"))[:500],
                                "char_start": source.get("char_start"),
                                "char_end": source.get("char_end"),
                            })
                    conflicts.append({
                        "event_ids": [pair[0].get("event_id"), pair[1].get("event_id")],
                        "dates": sorted(dates),
                        "event_type": key[0],
                        "review_required": True,
                        "interpretation": "possible_date_conflict",
                        "message": "برای رویدادهای دارای متن مشابه، تاریخ‌های متفاوتی دیده شده است؛ پیش از نتیجه‌گیری، اسناد و زمینه بررسی شوند.",
                        "sources": conflict_sources[:12],
                    })
                    break
    return conflicts


def _sort_key(e: Dict[str, Any]):
    d=e.get("date") or {}
    if d.get("range_start"):
        return (0, d.get("range_start"), d.get("range_end") or d.get("range_start"))
    return (1, "9999-99-99", "9999-99-99")


def build_case_chronology(uid: int, cid: int, include_undated: bool = True) -> Dict[str, Any]:
    """Build a current-document, source-linked chronology with no external AI."""
    case = get_case(uid, int(cid))
    if not case:
        return {"version": 151, "case_id": int(cid), "events": [], "api_used": False, "error": "case_not_found"}
    events=[]
    docs=get_case_documents(uid, int(cid))
    for meta in docs:
        text=_clean(meta.get("extracted_text"))
        if not text:
            continue
        events.extend(_extract_doc_events(meta, text))
    # Stable de-duplication, then assign deterministic IDs.
    events=_merge_duplicates(events)
    events.sort(key=_sort_key)
    for idx,e in enumerate(events,1):
        e["event_id"] = f"evt-{idx:04d}"
    conflicts=_detect_date_conflicts(events)
    critical=[e for e in events if e.get("event_type") in {"filing","service","hearing","judgment","appeal","execution","termination","breach"}]
    undated=[e for e in events if e.get("status")==STATUS_UNDATED]
    dated=[e for e in events if e.get("date",{}).get("gregorian_date")]
    return {
        "version": 151,
        "case_id": int(cid),
        "case_name": _clean(case.get("file_name")),
        "events": events if include_undated else dated,
        "critical_events": critical[:80],
        "conflicts": conflicts,
        "gaps": [{"type":"undated_event", "event_id":e.get("event_id"), "title":e.get("title")} for e in undated[:30]],
        "date_range": {
            "start": min((e["date"]["gregorian_date"] for e in dated), default=None),
            "end": max((e["date"]["gregorian_date"] for e in dated), default=None),
        },
        "counts": {
            "events": len(events),
            "verified": sum(1 for e in events if e.get("status")==STATUS_VERIFIED),
            "assertions": sum(1 for e in events if e.get("status")==STATUS_ASSERTION),
            "uncertain": sum(1 for e in events if e.get("status")==STATUS_UNCERTAIN),
            "conflict": sum(1 for e in events if e.get("status")==STATUS_CONFLICT),
            "inferred": sum(1 for e in events if e.get("status")==STATUS_INFERRED),
            "undated": len(undated),
        },
        "api_used": False,
        "resolver_path": ["case_db", "current_case_documents", "local_date_extraction", "event_classification", "deduplication", "conflict_detection", "provenance"],
        "historical_versions_excluded": bool(get_case_versions(uid, int(cid))),
    }


def format_chronology(chronology: Dict[str, Any], limit: int = 18) -> str:
    c=chronology or {}; events=c.get("events") or []; counts=c.get("counts") or {}
    lines=["🕘 خط زمانی حقوقی پرونده", "", f"رویدادها: {counts.get('events',0)} | تأییدشده: {counts.get('verified',0)} | ادعا: {counts.get('assertions',0)} | تعارض: {counts.get('conflict',0)} | بدون تاریخ: {counts.get('undated',0)}", ""]
    for e in events[:max(1,limit)]:
        d=e.get("date") or {}; label=d.get("jalali_date") or "تاریخ نامشخص"; status=e.get("status")
        icon={STATUS_VERIFIED:"🟢",STATUS_ASSERTION:"🔵",STATUS_UNCERTAIN:"🟡",STATUS_CONFLICT:"🟠",STATUS_INFERRED:"🟣",STATUS_UNDATED:"⚪"}.get(status,"⚪")
        src=(e.get("sources") or [{}])[0]
        src_label=f"{src.get('document_name','سند')}" + (f"، ص.{src.get('page')}" if src.get('page') else "")
        if src.get('char_start') is not None:
            src_label += f"، محل متن {src.get('char_start')}–{src.get('char_end')}"
        lines.append(f"{icon} {label} — {e.get('title','رویداد')}")
        lines.append(f"   {_clean(e.get('description'))[:260]}")
        lines.append(f"   📄 {src_label}")
    if len(events)>limit:
        lines.append(f"\n… {len(events)-limit} رویداد دیگر")
    if c.get("conflicts"):
        lines += ["", "⚠️ تعارض‌های زمانی نیازمند بررسی:"]
        for x in c["conflicts"][:5]: lines.append(f"• {x.get('event_type')}: {', '.join(x.get('dates') or [])}")
    lines += ["", "ℹ️ تاریخ‌های پرونده با تقویم شمسی/میلادی استاندارد می‌شوند؛ زمان پیام تلگرام جزو تاریخ رویداد حقوقی محسوب نمی‌شود."]
    return "\n".join(lines)
