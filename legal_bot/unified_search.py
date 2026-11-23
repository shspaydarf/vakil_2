"""Owner-scoped, local-first unified search for MACHINA.

Searches a lawyer's workspace and shared legal references without sending
private case content to an external model. Every workspace SQL query is scoped
by the authenticated user and active case ownership.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import db
from .analysis import search_text_with_pages

SCOPES = {
    "cases": "پرونده‌ها",
    "documents": "اسناد و نسخه‌ها",
    "notes": "یادداشت‌ها",
    "tasks": "کارها و رویدادها",
    "ai": "تاریخچه دستیار هوشمند",
    "drafts": "پیش‌نویس‌ها و خروجی‌ها",
    "clients": "موکلین",
    "library": "کتابخانه شخصی",
    "laws": "منابع حقوقی",
    "glossary": "واژه‌نامه",
}
DEFAULT_SCOPES = tuple(SCOPES)


def _norm(value: Any) -> str:
    text = str(value or "").replace("ي", "ی").replace("ى", "ی").replace("ك", "ک")
    text = text.replace("ۀ", "هٔ").replace("ة", "ه").replace("ؤ", "و").replace("إ", "ا").replace("أ", "ا").replace("ٱ", "ا")
    text = text.replace("\u200c", " ").replace("\u200d", " ").replace("\u200e", "").replace("\u200f", "")
    text = re.sub(r"[\u064B-\u065F\u0670\u06D6-\u06ED\u0640]", "", text)
    text = text.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    text = re.sub(r"\s+", " ", text).strip().casefold()
    return text


def _tokens(query: str) -> List[str]:
    return [x for x in re.findall(r"[\w\u0600-\u06FF]+", _norm(query)) if len(x) > 1]


def _snippet(text: str, query: str, width: int = 420) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    normalized = _norm(raw)
    q = _norm(query)
    pos = normalized.find(q) if q else -1
    if pos < 0:
        tokens = _tokens(query)
        positions = [normalized.find(t) for t in tokens if normalized.find(t) >= 0]
        pos = min(positions) if positions else 0
    start = max(0, pos - width // 3)
    end = min(len(raw), start + width)
    excerpt = raw[start:end].strip()
    return ("…" if start else "") + excerpt + ("…" if end < len(raw) else "")


def _relevance_bonus(text: Any, query: str) -> int:
    """Prefer exact phrases and fuller token coverage over loose partial hits."""
    hay = _norm(text)
    q = _norm(query)
    terms = _tokens(query)
    bonus = 0
    if q and q in hay:
        bonus += 40
    if terms:
        coverage = sum(1 for term in terms if term in hay)
        bonus += round(24 * coverage / len(terms))
    return bonus


def _matches(text: Any, query: str) -> bool:
    hay = _norm(text)
    if not hay:
        return False
    q = _norm(query)
    if q and q in hay:
        return True
    terms = _tokens(query)
    return bool(terms) and sum(1 for term in terms if term in hay) >= max(1, min(2, len(terms)))


def _table_exists(conn, name: str) -> bool:
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())


def _item(kind: str, title: str, body: str, query: str, *, case_id=None,
          case_name="", source_id=None, page=None, line=None, created_at="",
          locator="", score=0, citation_id=None) -> Dict[str, Any]:
    return {
        "kind": kind, "source": SCOPES.get(kind, kind), "title": str(title or "بدون عنوان")[:240],
        "snippet": _snippet(body or title, query), "case_id": case_id,
        "case_name": str(case_name or "")[:180], "source_id": source_id,
        "page": page, "line": line, "locator": locator,
        "created_at": str(created_at or ""), "score": int(score),
        "citation_id": citation_id,
    }


def _text_hits(kind: str, title: str, body: str, query: str, **meta) -> List[Dict[str, Any]]:
    if not body or not str(body).strip():
        return []
    meta = dict(meta)
    meta["score"] = int(meta.get("score", 0)) + _relevance_bonus(body, query)
    # Search page markers where available; otherwise provide a snippet without
    # inventing pagination. The analysis helper preserves verified page labels.
    try:
        hits = search_text_with_pages(str(body), query, max_results=4)
    except Exception:
        hits = []
    if hits:
        return [_item(kind, title, h.get("snippet") or h.get("text") or body, query,
                      page=h.get("page"), line=h.get("line"), **meta) for h in hits]
    if _matches(body, query):
        raw = str(body)
        page = None
        line = None
        # Preserve only explicit page markers found in the extracted text.
        qtokens = _tokens(query)
        match_pos = -1
        norm_raw = _norm(raw)
        norm_query = _norm(query)
        match_pos = norm_raw.find(norm_query)
        if match_pos < 0:
            positions = [norm_raw.find(t) for t in qtokens if norm_raw.find(t) >= 0]
            match_pos = min(positions) if positions else -1
        if match_pos >= 0:
            prefix = raw[:match_pos]
            page_markers = list(re.finditer(r"\[\s*صفحه\s*([0-9۰-۹]+)\s*\]", prefix))
            if page_markers:
                page_raw = page_markers[-1].group(1).translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
                try: page = int(page_raw)
                except ValueError: page = None
            line = raw[:match_pos].count("\n") + 1
        return [_item(kind, title, body, query, page=page, line=line, **meta)]
    return []


def search_user_workspace(uid: int, query: str, *, scopes: Optional[Sequence[str]] = None,
                          limit: int = 40, include_archived: bool = False) -> Dict[str, Any]:
    """Search local workspace + shared legal data. Never trusts a client scope ID."""
    uid = int(uid)
    query = str(query or "").strip()
    if len(query) < 2 or len(query) > 200:
        raise ValueError("عبارت جست‌وجو باید بین ۲ تا ۲۰۰ نویسه باشد.")
    requested = tuple(dict.fromkeys(DEFAULT_SCOPES if scopes is None else scopes))
    unknown = set(requested) - set(SCOPES)
    if unknown:
        raise ValueError("محدوده جست‌وجو نامعتبر است.")
    include_archived = bool(include_archived)
    results: List[Dict[str, Any]] = []
    with db.conn() as c:
        case_filter = "" if include_archived else " AND COALESCE(c.status,'')!='archived'"
        cases = c.execute("SELECT c.id,c.file_name,c.status,c.result,c.created_at,c.updated_at FROM cases c WHERE c.user_id=?" + case_filter + " ORDER BY COALESCE(c.updated_at,c.created_at) DESC", (uid,)).fetchall()
        case_map = {int(r["id"]): dict(r) for r in cases}

        if "cases" in requested:
            for row in cases:
                d = dict(row); body = " ".join(str(d.get(k) or "") for k in ("file_name", "status", "result"))
                if _matches(body, query):
                    results.append(_item("cases", d.get("file_name") or f"پرونده #{d['id']}", body, query,
                        case_id=d["id"], case_name=d.get("file_name"), source_id=d["id"],
                        created_at=d.get("updated_at") or d.get("created_at"), score=110 if _norm(query) in _norm(d.get("file_name")) else 80))

        if "documents" in requested:
            for table, id_col in (("case_documents", "id"), ("case_versions", "id")):
                if not _table_exists(c, table):
                    continue
                rows = c.execute(f"SELECT x.id,x.case_id,x.file_name,x.extracted_text,x.created_at,c.file_name AS case_name FROM {table} x JOIN cases c ON c.id=x.case_id WHERE c.user_id=?" + case_filter + " ORDER BY x.id DESC", (uid,)).fetchall()
                for row in rows:
                    d = dict(row); cid = int(d["case_id"])
                    results.extend(_text_hits("documents", d.get("file_name") or "سند", d.get("extracted_text") or "", query,
                        case_id=cid, case_name=d.get("case_name"), source_id=d.get("id"), created_at=d.get("created_at"), score=100))

        if "notes" in requested and _table_exists(c, "case_lawyer_notes"):
            rows = c.execute("SELECT n.case_id,n.note_text,n.updated_at,c.file_name AS case_name FROM case_lawyer_notes n JOIN cases c ON c.id=n.case_id WHERE n.user_id=? AND c.user_id=?" + case_filter, (uid, uid)).fetchall()
            for row in rows:
                d=dict(row); results.extend(_text_hits("notes", "یادداشت پرونده", d.get("note_text"), query, case_id=d["case_id"], case_name=d.get("case_name"), source_id=d["case_id"], created_at=d.get("updated_at"), score=95))

        if "tasks" in requested:
            if _table_exists(c, "case_tasks"):
                rows=c.execute("SELECT t.id,t.case_id,t.title,t.due_at,t.created_at,c.file_name AS case_name FROM case_tasks t JOIN cases c ON c.id=t.case_id WHERE t.user_id=? AND c.user_id=?" + case_filter + " ORDER BY t.id DESC", (uid,uid)).fetchall()
                for row in rows:
                    d=dict(row); body=" ".join(str(d.get(k) or "") for k in ("title","due_at"))
                    if _matches(body,query): results.append(_item("tasks",d.get("title"),body,query,case_id=d["case_id"],case_name=d.get("case_name"),source_id=d["id"],created_at=d.get("created_at"),locator=d.get("due_at"),score=75))
            if _table_exists(c, "case_events"):
                rows=c.execute("SELECT e.id,e.case_id,e.title,e.details,e.created_at,c.file_name AS case_name FROM case_events e JOIN cases c ON c.id=e.case_id WHERE e.user_id=? AND c.user_id=?" + case_filter + " ORDER BY e.id DESC",(uid,uid)).fetchall()
                for row in rows:
                    d=dict(row); body=" ".join(str(d.get(k) or "") for k in ("title","details"))
                    if _matches(body,query): results.append(_item("tasks",d.get("title"),body,query,case_id=d["case_id"],case_name=d.get("case_name"),source_id=d["id"],created_at=d.get("created_at"),score=70))

        if "ai" in requested and _table_exists(c, "case_ai_history"):
            rows=c.execute("SELECT h.id,h.case_id,h.question,h.answer,h.created_at,c.file_name AS case_name FROM case_ai_history h JOIN cases c ON c.id=h.case_id WHERE h.user_id=? AND c.user_id=?" + case_filter + " ORDER BY h.id DESC",(uid,uid)).fetchall()
            for row in rows:
                d=dict(row); body="\n".join((d.get("question") or "",d.get("answer") or ""))
                results.extend(_text_hits("ai",d.get("question") or "گفت‌وگوی دستیار",body,query,case_id=d["case_id"],case_name=d.get("case_name"),source_id=d["id"],created_at=d.get("created_at"),score=65))

        if "drafts" in requested and _table_exists(c, "drafting_artifacts"):
            rows=c.execute("SELECT d.id,d.case_id,d.brief_type,d.draft_text,d.version_no,d.created_at,d.updated_at,c.file_name AS case_name FROM drafting_artifacts d JOIN cases c ON c.id=d.case_id WHERE d.user_id=? AND c.user_id=?" + case_filter + " ORDER BY d.updated_at DESC",(uid,uid)).fetchall()
            for row in rows:
                d=dict(row); results.extend(_text_hits("drafts",f"{d.get('brief_type') or 'پیش‌نویس'} · نسخه {d.get('version_no')}",d.get("draft_text"),query,case_id=d["case_id"],case_name=d.get("case_name"),source_id=d["id"],created_at=d.get("updated_at"),score=85))

        if "clients" in requested and _table_exists(c, "clients"):
            rows=c.execute("SELECT id,name,note,updated_at FROM clients WHERE user_id=? ORDER BY updated_at DESC",(uid,)).fetchall()
            for row in rows:
                d=dict(row); body=" ".join((d.get("name") or "",d.get("note") or ""))
                if _matches(body,query): results.append(_item("clients",d.get("name"),body,query,source_id=d["id"],created_at=d.get("updated_at"),score=70))

        if "library" in requested and _table_exists(c, "lawyer_library_items"):
            rows=c.execute("SELECT id,title,category,description,content,updated_at FROM lawyer_library_items WHERE user_id=? ORDER BY updated_at DESC",(uid,)).fetchall()
            for row in rows:
                d=dict(row); body=" ".join(str(d.get(k) or "") for k in ("title","category","description","content"))
                results.extend(_text_hits("library",d.get("title"),body,query,source_id=d["id"],created_at=d.get("updated_at"),score=60))

    # Shared legal resources are intentionally separate from the private workspace.
    if "laws" in requested:
        try:
            from .laws import search as law_search
            for rec in law_search(query, min(12, limit)):
                citation=rec.get("citation") or {}
                body=rec.get("clean_text") or rec.get("text") or rec.get("question") or ""
                results.append(_item("laws",rec.get("title") or rec.get("law") or "منبع حقوقی",body,query,
                    source_id=citation.get("id"),page=citation.get("page") or rec.get("source_page"),
                    locator=rec.get("article") or rec.get("ruling_number") or rec.get("consultation_number") or "",
                    created_at=rec.get("date") or rec.get("year") or "",score=90,citation_id=citation.get("id")))
        except Exception:
            # A missing/temporarily unavailable law index must not break private search.
            pass

    if "glossary" in requested:
        try:
            from .glossary import lookup as glossary_lookup
            for rec in glossary_lookup(query, min(8, limit)):
                results.append(_item("glossary",rec.get("term") or rec.get("title") or "اصطلاح حقوقی",
                    rec.get("definition") or rec.get("text") or rec.get("description") or "",query,
                    source_id=rec.get("id"),score=50))
        except Exception:
            pass

    # Deduplicate identical source records and sort by deterministic source score.
    unique: Dict[Tuple[str,str,str], Dict[str,Any]] = {}
    for item in results:
        key=(item["kind"],str(item.get("source_id") or ""),str(item.get("page") or ""))
        old=unique.get(key)
        if old is None or item.get("score",0)>old.get("score",0): unique[key]=item
    # Stable two-pass sort: relevance score first, then newest records first.
    ordered = sorted(unique.values(), key=lambda x: str(x.get("created_at") or ""), reverse=True)
    ordered.sort(key=lambda x: -int(x.get("score") or 0))
    total_count = len(ordered)
    counts=Counter(x["kind"] for x in ordered)
    ordered = ordered[:max(1, min(int(limit), 60))]
    return {
        "query":query,"items":ordered,"count":len(ordered),"total_count":total_count,
        "source_counts":[{"kind":k,"label":SCOPES.get(k,k),"count":v} for k,v in counts.items()],
        "scopes":list(requested),"include_archived":include_archived,
        "notice":"جست‌وجو محلی و مبتنی بر متن/تطبیق واژگانی است؛ رتبه‌بندی، کامل‌بودن سند یا اعتبار حقوقی منبع را تضمین نمی‌کند.",
        "coverage_note":"همه رکوردهای قابل‌دسترسی حساب در محدوده‌های انتخاب‌شده بررسی می‌شوند؛ فقط حداکثر تعداد نتیجه درخواستی نمایش داده می‌شود. فایل اسکن‌شده یا متن استخراج‌نشده در نتایج نیست.",
        "privacy_note":"اطلاعات فضای کاری فقط با شناسه حساب احراز‌شده جست‌وجو شده است و برای این جست‌وجو به AI خارجی ارسال نشده است.",
    }
