# -*- coding: utf-8 -*-
"""V150 — local-first case information resolver.

This layer resolves the information needed by the brief planner before any
source selection or drafting.  It deliberately prefers structured case data,
document extraction, deterministic analysis and local search.  An external
LLM is not called by this module.
"""
from __future__ import annotations

from .text_utils import clean_whitespace as _clean

import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .analysis import analyze, local_case_search_v5
from .brief_planner import build_brief_plan
from .brief_templates import TEMPLATES
from .db import get_case, get_case_documents, get_case_versions, get_case_text

STATUS_VERIFIED = "verified"
STATUS_UNCERTAIN = "uncertain"
STATUS_MISSING = "missing"
STATUS_CONFLICT = "conflict"

IMPORTANCE_REQUIRED = "required"
IMPORTANCE_IMPORTANT = "important"
IMPORTANCE_OPTIONAL = "optional"




def _norm(value: Any) -> str:
    return _clean(value).replace("ي", "ی").replace("ك", "ک").lower()


def _unique(values: Iterable[str], limit: int = 8) -> List[str]:
    out: List[str] = []
    seen = set()
    for value in values:
        value = _clean(value)
        key = _norm(value)
        if value and key not in seen:
            seen.add(key)
            out.append(value)
        if len(out) >= limit:
            break
    return out


def _source(kind: str, label: str, **extra: Any) -> Dict[str, Any]:
    result = {"type": kind, "label": _clean(label)}
    result.update({k: v for k, v in extra.items() if v not in (None, "", [])})
    return result


def _doc_sources(uid: int, cid: int) -> List[Tuple[Dict[str, Any], str]]:
    """Return current case documents only.

    case_versions are historical comparison artifacts, not current evidence.
    Mixing them into fact resolution can create false conflicts when a later
    version intentionally changes a date, amount, party, or claim. Historical
    versions remain available to the dedicated version-diff workflow.
    """
    rows: List[Tuple[Dict[str, Any], str]] = []
    for doc in get_case_documents(uid, cid):
        text = _clean(doc.get("extracted_text"))
        if text:
            meta = dict(doc)
            meta["source_type"] = "case_document"
            rows.append((meta, text))
    return rows


def _extract_evidence_for_item(item: str, text: str, limit: int = 3) -> List[Dict[str, Any]]:
    queries = {
        "parties": ["خواهان خوانده شاکی مشتکی عنه موکل موجر مستأجر زوج زوجه"],
        "subject": ["خواسته مطالبه تقاضا درخواست موضوع محکومیت الزام اعتراض دفاع"],
        "forum": ["دادگاه شعبه دادسرا دیوان عدالت اداری اجرای احکام مرجع"],
        "key_date": ["تاریخ مورخ سررسید ابلاغ مهلت موعد"],
        "main_evidence": ["سند مدرک رسید قرارداد اظهارنامه شهادت کارشناس دادنامه رأی گواهی"],
        "appeal_decision": ["دادنامه رأی حکم شماره دادنامه"],
    }
    hits: List[Dict[str, Any]] = []
    for query in queries.get(item, [item]):
        try:
            hits.extend(local_case_search_v5(text, query, max_results=limit))
        except Exception:
            continue
        if hits:
            break
    seen = set()
    out = []
    for hit in hits:
        snippet = _clean(hit.get("snippet") or hit.get("text"))[:900]
        page = hit.get("page")
        key = (page, snippet)
        if not snippet or key in seen:
            continue
        seen.add(key)
        out.append({"page": page, "text": snippet, "score": hit.get("score", 0)})
        if len(out) >= limit:
            break
    return out


def _item(key: str, label: str, importance: str, value: Any = "", status: str = STATUS_MISSING,
          sources: Optional[List[Dict[str, Any]]] = None, confidence: float = 0.0,
          notes: Optional[List[str]] = None) -> Dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "importance": importance,
        "value": value,
        "status": status,
        "sources": sources or [],
        "confidence": round(max(0.0, min(1.0, float(confidence))), 3),
        "confirmed_by_user": False,
        "notes": notes or [],
    }


def _required_items(brief_type: str, template_key: str = "") -> List[Tuple[str, str, str]]:
    items = [
        ("parties", "طرفین و سمت‌ها", IMPORTANCE_REQUIRED),
        ("subject", "موضوع/خواسته", IMPORTANCE_REQUIRED),
        ("forum", "مرجع رسیدگی", IMPORTANCE_IMPORTANT),
        ("key_date", "تاریخ/مهلت مهم", IMPORTANCE_IMPORTANT),
        ("main_evidence", "دلیل یا مستند اصلی", IMPORTANCE_REQUIRED),
    ]
    if "تجدیدنظر" in _norm(brief_type) or "اعتراض" in _norm(brief_type):
        items.append(("appeal_decision", "دادنامه/رأی مورد اعتراض", IMPORTANCE_REQUIRED))
    profile = TEMPLATES.get(template_key or "", {}) if template_key else {}
    for field in profile.get("required", []) if isinstance(profile, dict) else []:
        key = "template:" + re.sub(r"[^a-zA-Z0-9_]+", "_", str(field)).strip("_").lower()
        items.append((key, f"قالب: {field}", IMPORTANCE_IMPORTANT))
    # preserve order while removing duplicate keys
    out = []
    seen = set()
    for row in items:
        if row[0] not in seen:
            seen.add(row[0])
            out.append(row)
    return out


def _values_from_analysis(info: Dict[str, Any], key: str) -> List[str]:
    if key == "parties":
        return [f"{_clean(x.get('role'))} {_clean(x.get('name'))}" for x in info.get("parties", []) if isinstance(x, dict)]
    if key == "subject":
        vals = []
        vals.extend(_clean(x.get("claim") or x.get("text")) for x in info.get("claims", []) if isinstance(x, dict))
        vals.extend(_clean(x.get("text")) for x in info.get("remedies", []) if isinstance(x, dict))
        return vals
    if key == "forum":
        return [_clean(x.get("value")) for x in info.get("courts", []) if isinstance(x, dict)]
    if key == "key_date":
        return [_clean(x.get("value")) for x in info.get("dates", []) if isinstance(x, dict)]
    if key == "main_evidence":
        return [_clean(x.get("text") or x.get("value")) for x in info.get("evidence", []) if isinstance(x, dict)]
    if key == "appeal_decision":
        vals = []
        vals.extend(_clean(x.get("value")) for x in info.get("courts", []) if isinstance(x, dict))
        vals.extend(_clean(x.get("text")) for x in info.get("claims", []) if isinstance(x, dict) and re.search(r"رأی|دادنامه|حکم", _clean(x.get("text"))))
        return vals
    return []


def _build_item_from_text(key: str, label: str, importance: str, infos: List[Tuple[Dict[str, Any], Dict[str, Any], str]]) -> Dict[str, Any]:
    values: List[str] = []
    sources: List[Dict[str, Any]] = []
    for source_meta, info, text in infos:
        extracted = _values_from_analysis(info, key)
        values.extend(extracted)
        if extracted:
            source_kind = source_meta.get("source_type") or ("lawyer_input" if not source_meta.get("id") else "case_document")
            src = _source(
                source_kind,
                source_meta.get("file_name") or ("اطلاعات واردشده توسط وکیل" if source_kind == "lawyer_input" else f"سند #{source_meta.get('id', '?')}"),
                document_id=source_meta.get("id"),
                page_count=source_meta.get("page_count"),
            )
            # Keep a small, traceable evidence trail. We deliberately do not
            # claim an exact page unless the extractor supplied one.
            evidence = _extract_evidence_for_item(key, text, limit=2)
            if not evidence and text:
                page_match = re.search(r"\[صفحه\s+(\d+)\]", text)
                evidence = [{"page": int(page_match.group(1)) if page_match else None,
                             "text": text[:900], "score": 0.0, "method": "source_fallback"}]
            if evidence:
                src["evidence"] = evidence
            if src not in sources:
                sources.append(src)
    values = _unique(values, 8)
    if not values:
        return _item(key, label, importance)
    # Multiple values are not automatically contradictory. Parties, claims,
    # evidence and dates commonly have multiple legitimate entries. They stay
    # UNCERTAIN until an explicit contradiction is detected.
    status = STATUS_VERIFIED if len(values) == 1 else STATUS_UNCERTAIN
    confidence = 0.92 if status == STATUS_VERIFIED else 0.62
    notes = []
    if status == STATUS_UNCERTAIN:
        notes.append("چند مقدار مرتبط در منابع پیدا شد؛ این مورد تا زمان تأیید وکیل قطعی تلقی نمی‌شود.")
    return _item(key, label, importance, values[0] if len(values) == 1 else values, status, sources, confidence, notes)


def _detect_local_conflicts(items: List[Dict[str, Any]], infos: List[Tuple[Dict[str, Any], Dict[str, Any], str]]) -> List[Dict[str, Any]]:
    """Detect only evidence of contradiction, not mere multiplicity.

    Multiple parties, dates, claims, documents, or authorities are normal in a
    legal matter. They are UNCERTAIN when not resolved, but must not be promoted
    to CONFLICT merely because there is more than one value.
    """
    conflicts: List[Dict[str, Any]] = []
    combined = "\n".join(text for _meta, _info, text in infos)

    # Explicit lexical contradiction for payment/non-payment signals.
    positive = bool(re.search(r"پرداخت\s+(?:شد|شده|گردید|انجام\s+شد)|واریز\s+(?:شد|شده)", combined))
    negative = bool(re.search(r"(?:پرداخت|واریز)\s+(?:نشده|نشد|نکرد|نکرده)|عدم\s+پرداخت|پرداخت\s+نکرد", combined))
    if positive and negative:
        conflicts.append({
            "key": "payment_status",
            "label": "وضعیت پرداخت",
            "values": ["نشانه پرداخت", "نشانه عدم پرداخت"],
            "message": "در متن پرونده هم نشانه پرداخت و هم نشانه عدم پرداخت دیده شد.",
        })

    # A small set of explicit negation contradictions for the same proposition.
    contradiction_pairs = [
        (r"قرارداد\s+(?:وجود\s+دارد|منعقد\s+شده)", r"(?:قرارداد\s+)?(?:وجود\s+ندارد|منعقد\s+نشده)"),
        (r"ابلاغ\s+(?:شد|شده|گردید)", r"ابلاغ\s+(?:نشده|نشد|نگردید)") ,
    ]
    for pos_pat, neg_pat in contradiction_pairs:
        if re.search(pos_pat, combined) and re.search(neg_pat, combined):
            key = "contract_existence" if "قرارداد" in pos_pat else "service_of_notice"
            label = "وجود قرارداد" if key == "contract_existence" else "وضعیت ابلاغ"
            conflicts.append({
                "key": key, "label": label,
                "values": ["اظهار مثبت", "اظهار منفی"],
                "message": f"در متن پرونده درباره «{label}» دو گزاره متناقض پیدا شد.",
            })
    return conflicts


def resolve_case_information(uid: int, cid: Optional[int], brief_type: str = "لایحه دفاعیه",
                              facts: str = "", template_key: str = "",
                              confirmed_answers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Resolve brief prerequisites without external AI.

    If no case is selected, only the supplied facts are analyzed. With a case,
    all extracted documents and versions are analyzed independently so that
    provenance can be preserved.
    """
    facts = _clean(facts)
    case = get_case(uid, int(cid)) if cid else None
    case_text = get_case_text(uid, int(cid)) if case else ""
    source_rows = _doc_sources(uid, int(cid)) if case else []

    infos: List[Tuple[Dict[str, Any], Dict[str, Any], str]] = []
    if source_rows:
        for meta, text in source_rows:
            try:
                infos.append((meta, analyze(text), text))
            except Exception:
                continue
    if facts:
        try:
            infos.append(({"id": None, "file_name": "اطلاعات واردشده توسط وکیل"}, analyze(facts), facts))
        except Exception:
            pass
    if not infos and (facts or case_text):
        text = facts or case_text
        try:
            infos.append(({"id": None, "file_name": "متن پرونده"}, analyze(text), text))
        except Exception:
            pass

    plan = build_brief_plan(facts=facts, brief_type=brief_type, case_text=case_text, template_key=template_key)
    items: List[Dict[str, Any]] = []
    for key, label, importance in _required_items(brief_type, template_key):
        if key.startswith("template:"):
            # Template fields are intentionally not guessed. The planner's gap
            # detector remains the authority for literal template requirements.
            items.append(_item(key, label, importance))
            continue
        item = _build_item_from_text(key, label, importance, infos)
        if item["status"] == STATUS_MISSING:
            evidence = _extract_evidence_for_item(key, facts or case_text)
            if evidence:
                item["sources"] = [_source("local_search", "جستجوی محلی پرونده", hits=evidence)]
                item["value"] = evidence[0]["text"]
                item["status"] = STATUS_UNCERTAIN
                item["confidence"] = 0.58
                item["notes"] = ["نشانه متنی پیدا شد، اما استخراج ساختاری کافی برای تأیید قطعی نیست."]
        items.append(item)

    conflicts = _detect_local_conflicts(items, infos)
    for conflict in conflicts:
        item = next((x for x in items if x.get("key") == conflict.get("key")), None)
        if item:
            item.setdefault("notes", []).append(conflict["message"])

    # Planner gaps are still useful, but V150 classifies them by importance.
    missing_labels = {x.get("label") for x in items if x.get("status") == STATUS_MISSING}
    questions = []
    for item in items:
        if item.get("status") in {STATUS_MISSING, STATUS_CONFLICT} and item.get("importance") == IMPORTANCE_REQUIRED:
            questions.append({
                "key": item["key"],
                "label": item["label"],
                "question": _question_for_item(item),
            })
    for gap in plan.get("missing", []):
        if gap not in missing_labels and len(questions) < 8:
            questions.append({"key": "planner:" + _norm(gap), "label": gap, "question": f"اطلاعات «{gap}» را در صورت وجود تکمیل کنید."})

    # Lawyer-confirmed answers are authoritative for this workflow and must
    # survive every re-resolution pass. They are merged after extraction so a
    # fresh analysis cannot overwrite them with an older/missing extraction.
    for key, answer in (confirmed_answers or {}).items():
        answer = _clean(answer)
        if not answer:
            continue
        item = next((x for x in items if x.get("key") == key), None)
        if item:
            item["value"] = answer
            item["status"] = STATUS_VERIFIED
            item["confidence"] = 1.0
            item["confirmed_by_user"] = True
            item["sources"] = [_source("lawyer_input", "تأیید/ورودی وکیل")]
            item.setdefault("notes", []).append("این مقدار توسط وکیل تأیید شده و بر استخراج مجدد اولویت دارد.")
    # Remove questions already answered by the lawyer.
    confirmed_keys = set((confirmed_answers or {}).keys())
    questions = [q for q in questions if q.get("key") not in confirmed_keys]

    counts = {s: sum(1 for x in items if x.get("status") == s) for s in (STATUS_VERIFIED, STATUS_UNCERTAIN, STATUS_CONFLICT, STATUS_MISSING)}
    required_missing = sum(1 for x in items if x.get("importance") == IMPORTANCE_REQUIRED and x.get("status") in {STATUS_MISSING, STATUS_CONFLICT})
    return {
        "version": 150,
        "case_id": int(cid) if cid else None,
        "brief_type": _clean(brief_type) or "لایحه دفاعیه",
        "template_key": template_key or "",
        "case_name": _clean((case or {}).get("file_name")) if case else "",
        "items": items,
        "conflicts": conflicts,
        "questions": questions,
        "counts": counts,
        "required_missing": required_missing,
        "ready_for_review": required_missing == 0 and not any(x.get("status") == STATUS_CONFLICT for x in items if x.get("importance") == IMPORTANCE_REQUIRED),
        "api_used": False,
        "resolver_path": ["case_db", "current_case_documents", "local_analysis", "local_search", "deterministic_conflict_check", "lawyer_confirmation_overlay"],
        "historical_versions_excluded": bool(cid and get_case_versions(uid, int(cid))),
    }


def _question_for_item(item: Dict[str, Any]) -> str:
    mapping = {
        "parties": "نام و سمت دقیق طرفین پرونده چیست؟",
        "subject": "موضوع یا خواسته دقیق این لایحه چیست؟",
        "forum": "مرجع رسیدگی، شعبه و در صورت وجود شماره پرونده چیست؟",
        "key_date": "مهم‌ترین تاریخ یا مهلت مرتبط با لایحه چیست؟",
        "main_evidence": "مهم‌ترین سند یا دلیل پشتیبان ادعا چیست؟",
        "appeal_decision": "شماره/تاریخ دادنامه یا رأی مورد اعتراض چیست؟",
    }
    return mapping.get(item.get("key"), f"اطلاعات «{item.get('label', 'این مورد')}» را وارد کنید.")


def apply_information_answer(resolver: Dict[str, Any], key: str, answer: str, confirmed: bool = True) -> Dict[str, Any]:
    data = dict(resolver or {})
    items = [dict(x) for x in (data.get("items") or [])]
    answer = _clean(answer)
    for item in items:
        if item.get("key") == key:
            item["value"] = answer
            if confirmed and answer:
                item["status"] = STATUS_VERIFIED
                item["confidence"] = 1.0
            else:
                # "I don't know" is not a fact and should remain missing so
                # required-field gating cannot silently treat it as complete.
                item["status"] = item.get("status") or STATUS_MISSING
                item["confidence"] = 0.0
            item["confirmed_by_user"] = bool(confirmed and answer)
            item["sources"] = [_source("lawyer_input", "تأیید/ورودی وکیل")] if answer else []
            item.setdefault("notes", []).append("این مقدار توسط وکیل وارد/تأیید شده است.") if answer else None
            break
    data["items"] = items
    data["questions"] = [q for q in data.get("questions", []) if q.get("key") != key]
    data["counts"] = {s: sum(1 for x in items if x.get("status") == s) for s in (STATUS_VERIFIED, STATUS_UNCERTAIN, STATUS_CONFLICT, STATUS_MISSING)}
    data["required_missing"] = sum(1 for x in items if x.get("importance") == IMPORTANCE_REQUIRED and x.get("status") in {STATUS_MISSING, STATUS_CONFLICT})
    data["ready_for_review"] = data["required_missing"] == 0 and not any(x.get("status") == STATUS_CONFLICT and x.get("importance") == IMPORTANCE_REQUIRED for x in items)
    return data


def format_information_map(resolver: Dict[str, Any]) -> str:
    r = resolver or {}
    icons = {STATUS_VERIFIED: "🟢", STATUS_UNCERTAIN: "🟡", STATUS_MISSING: "🔴", STATUS_CONFLICT: "🟠"}
    lines = ["🧠 تکمیل هوشمند اطلاعات پرونده", "", "اصل کار: ابتدا اطلاعات موجود در پرونده، اسناد و موتور تحلیل محلی بررسی شد؛ در این مرحله API خارجی استفاده نشده است.", ""]
    counts = r.get("counts") or {}
    lines.append(f"📊 پیدا شد: {counts.get(STATUS_VERIFIED,0)}  |  نیازمند بررسی: {counts.get(STATUS_UNCERTAIN,0)}  |  تعارض: {counts.get(STATUS_CONFLICT,0)}  |  پیدا نشد: {counts.get(STATUS_MISSING,0)}")
    for item in r.get("items") or []:
        icon = icons.get(item.get("status"), "⚪")
        value = item.get("value")
        if isinstance(value, list):
            value_text = " / ".join(_clean(x) for x in value[:3])
        else:
            value_text = _clean(value)
        if not value_text:
            value_text = "هنوز پیدا نشد"
        lines.append(f"{icon} {item.get('label')}: {value_text[:420]}")
        if item.get("notes"):
            lines.append(f"   ↳ {_clean(item['notes'][0])[:300]}")
    if r.get("conflicts"):
        lines += ["", "⚠️ تعارض‌های پیدا‌شده:"]
        for c in r["conflicts"][:5]:
            lines.append(f"• {c.get('label')}: {_clean(c.get('message'))}")
    questions = r.get("questions") or []
    if questions:
        q = questions[0]
        lines += ["", "❓ اولین مورد ضروری:", q.get("question", "")]
        lines.append("اگر پاسخ را نمی‌دانید، «نمی‌دانم» بنویسید؛ بات آن را به‌عنوان واقعیت ثبت نمی‌کند.")
    elif r.get("ready_for_review"):
        lines += ["", "✅ اطلاعات ضروری برای ادامه آماده است. قبل از انتخاب منابع، آن را بررسی و تأیید کنید."]
    return "\n".join(lines)
