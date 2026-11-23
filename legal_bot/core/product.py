"""Product-level case workflow contract.

PRODUCT-01 creates one UI-agnostic orchestration boundary for the future HTTP
API and Mini App. It does not duplicate legal reasoning; it composes the
existing case, chronology, legal-intelligence, AI-history and drafting layers.

The key rule is that AI is user-triggered, not silently invoked while opening a
case. The workspace therefore exposes the AI context/history that is already
available, while draft generation remains an explicit action.
"""
from __future__ import annotations

import json
import re

from typing import Any, Dict, Optional

from ..db import get_case_ai_history, get_case_documents, get_case_text
from ..drafting_artifacts import latest_draft_artifact, list_draft_artifacts
from ..timeline_engine import build_case_chronology
from ..issue_engine import build_case_issues
from ..evidence_engine import build_evidence_matrix
from ..authority_engine import build_case_authorities
from ..strategy_engine import build_case_strategies
from ..case_guidance import build_case_guidance
from .entitlements import EntitlementService
from ..ai import ask_ai_question, _sample_case_text
from ..ai_context_optimizer import select_records, select_document_pages
from ..config import AI_TEXT_MAX_CHARS
from ..db import add_case_ai_exchange
from ..drafting_workflow import run_drafting_workflow
from .documents import DocumentService


class ProductCaseError(ValueError):
    """Raised for invalid or inaccessible product-level case operations."""


def _uid(value: Any) -> int:
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise ProductCaseError("شناسه کاربر نامعتبر است.")
    if value <= 0:
        raise ProductCaseError("شناسه کاربر نامعتبر است.")
    return value


def _cid(value: Any) -> int:
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise ProductCaseError("شناسه پرونده نامعتبر است.")
    if value <= 0:
        raise ProductCaseError("شناسه پرونده نامعتبر است.")
    return value


def _digits_ascii(value: Any) -> str:
    return str(value or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))


def _audit_answer_page_citations(answer: str, case_text: str) -> Dict[str, Any]:
    """Check whether cited page labels exist in supplied text, not whether they support a claim.

    This deliberately narrow audit avoids presenting a page-number match as semantic proof.
    """
    answer = str(answer or "")
    case_text = str(case_text or "")
    normalize = lambda value: _digits_ascii(value).replace("ي", "ی").replace("ك", "ک")
    # Ingested documents use [صفحه N]. Accept common AI answer forms such as
    # «صفحه ۲»، «ص. 2» and «منبع: [صفحه 2]».
    known_pages = set(re.findall(r"\[\s*صفحه\s*(\d+)\s*\]", normalize(case_text), flags=re.IGNORECASE))
    cited_pages = set(re.findall(r"(?:صفحه|ص\.?)[\s:\[【#]*(\d+)", normalize(answer), flags=re.IGNORECASE))
    valid = sorted(cited_pages & known_pages, key=lambda x: int(x))
    unsupported = sorted(cited_pages - known_pages, key=lambda x: int(x))
    if not cited_pages:
        status = "no_page_citations"
    elif not known_pages:
        status = "cannot_validate_page_labels"
    elif unsupported and valid:
        status = "partially_matched_page_labels"
    elif unsupported:
        status = "unmatched_page_labels"
    else:
        status = "page_labels_exist"
    return {
        "status": status,
        "cited_pages": [int(x) for x in sorted(cited_pages, key=lambda x: int(x))],
        "page_labels_found_in_context": [int(x) for x in sorted(known_pages, key=lambda x: int(x))],
        "matched_page_labels": [int(x) for x in valid],
        "unmatched_page_labels": [int(x) for x in unsupported],
        "semantic_support_checked": False,
        "warning": "وجود شماره صفحه در متن پرونده فقط وجود برچسب صفحه را تأیید می‌کند، نه اینکه آن صفحه واقعاً ادعا را پشتیبانی کند.",
    }


def _build_intelligence_summary(chronology, issues, evidence, authorities, strategies, guidance, *, compact=False):
    """Create one stable, UI-friendly intelligence snapshot from existing engines."""
    conflicts = chronology.get("conflicts") or []
    issue_items = issues.get("issues") or []
    claims = evidence.get("claims") or []
    matrix = evidence.get("matrix") or []
    missing = guidance.get("missing") or []
    risks = guidance.get("risks") or []
    contradictions = guidance.get("contradictions") or []
    actions = guidance.get("actions") or []
    questions = guidance.get("questions") or []
    gaps = sum(1 for row in matrix if not (row.get("evidence") or []))
    risk_level = "high" if conflicts or contradictions or gaps else ("medium" if risks or missing else "low")
    findings = []
    for item in conflicts[:5]:
        findings.append({"type": "conflict", "severity": "high", "title": "تعارض زمانی", "text": str(item.get("message") or item.get("title") or item)[:500]})
    for item in contradictions[:5]:
        findings.append({"type": "contradiction", "severity": "high", "title": "تعارض در روایت/مدرک", "text": str(item.get("message") or item.get("text") or item)[:500]})
    for item in risks[:5]:
        text = item.get("text") if isinstance(item, dict) else str(item)
        findings.append({"type": "risk", "severity": "medium", "title": "ریسک قابل بررسی", "text": str(text)[:500]})
    for item in missing[:5]:
        findings.append({"type": "missing", "severity": "medium", "title": "خلأ اطلاعاتی", "text": str(item)[:500]})
    authority_items = authorities.get("authorities") or []
    authority_counts = authorities.get("counts") or {}
    unverified_authorities = sum(1 for item in authority_items if item.get("verification_status") != "verified")
    authority_gaps = int(authority_counts.get("authority_gaps") or 0)
    return {
        "risk_level": risk_level,
        # Text sufficiency is not legal correctness. Keep confidence low until
        # semantic entailment and source verification are independently evaluated.
        "confidence": "low",
        "confidence_basis": "rule_based_not_semantically_validated",
        "confidence_note": "کافی‌بودن متن ورودی به معنی صحت تحلیل حقوقی نیست؛ ارتباط معنایی ادعا و سند و اعتبار منبع هنوز نیازمند بررسی است.",
        "headline": (guidance.get("overview") or ["تحلیل اولیه پرونده آماده است."])[0],
        "finding_count": len(findings),
        "findings": findings[:10],
        "recommended_actions": [str(x)[:500] for x in actions[:8]],
        "open_questions": [str(x)[:500] for x in questions[:8]],
        "evidence_gaps": gaps,
        "source_count": len(guidance.get("source_stats") or {}) or len(claims),
        "legal_authority_count": len(authority_items),
        "unverified_legal_authority_count": unverified_authorities,
        "legal_authority_gaps": authority_gaps,
        "legal_authority_warning": "منابع قانونی بازیابی‌شده نامزد بررسی‌اند؛ حضور در corpus به‌تنهایی اعتبار روز، قابلیت اعمال یا صحت استناد را ثابت نمی‌کند.",
        "compact": compact,
    }

class ProductCaseService:
    """Canonical product-facing case workflow.

    ``workspace`` is the future API/Mini App read contract. It intentionally
    returns plain dictionaries and never exposes DB connections or Telegram
    state. Expensive deterministic legal analysis is composed once per request
    and returned as a coherent snapshot.
    """

    CONTRACT_VERSION = 2


    def workspace(self, user_id: int, case_id: int, *, include_deep_intelligence: bool = True,
                  history_limit: int = 5, draft_limit: int = 5) -> Dict[str, Any]:
        uid, cid = _uid(user_id), _cid(case_id)
        from .cases import CaseService

        case = CaseService().get(uid, cid)
        if not case:
            raise ProductCaseError("پرونده پیدا نشد.")

        documents = DocumentService().public_list(uid, cid)
        text = get_case_text(uid, cid) or ""
        if include_deep_intelligence:
            chronology = build_case_chronology(uid, cid, include_undated=True)
            issues = build_case_issues(uid, cid)
            evidence = build_evidence_matrix(uid, cid)
            authorities = build_case_authorities(uid, cid)
            strategies = build_case_strategies(uid, cid)
            guidance = build_case_guidance(text) if text.strip() else {"sufficient": False, "ai_used": False}
            intelligence = {
                "chronology": chronology, "issues": issues, "evidence": evidence,
                "authorities": authorities, "strategies": strategies, "guidance": guidance,
                "summary": _build_intelligence_summary(chronology, issues, evidence, authorities, strategies, guidance),
            }
        else:
            # A genuine lightweight path: do not invoke any intelligence engines.
            chronology = {"events": [], "conflicts": [], "counts": {}}
            issues = {"issues": [], "counts": {}}
            evidence = {"claims": [], "matrix": [], "counts": {}}
            authorities = {"authorities": [], "counts": {}}
            strategies = {"strategies": [], "counts": {}}
            guidance = {"sufficient": False, "ai_used": False}
            intelligence = {
                "chronology": chronology, "issues": issues, "evidence": evidence,
                "authorities": authorities, "strategies": strategies, "guidance": guidance,
                "summary": {"risk_level": "unknown", "confidence": "low", "confidence_basis": "not_computed_in_lightweight_mode", "findings": [], "recommended_actions": [], "open_questions": [], "compact": True},
            }

        history = get_case_ai_history(uid, cid, max(1, min(int(history_limit), 10)))
        drafts = list_draft_artifacts(uid, cid, max(1, min(int(draft_limit), 12)))
        dashboard = self._build_dashboard(
            uid, cid, case, documents, intelligence, drafts, history,
            include_deep_intelligence=include_deep_intelligence,
        )

        return {
            "contract_version": self.CONTRACT_VERSION,
            "case": case,
            "dashboard": dashboard,
            "documents": documents,
            "document_count": len(documents),
            "text_chars": len(text),
            "intelligence": intelligence,
            "ai": {
                "history": history,
                "history_count": len(history),
                "user_triggered": True,
                "auto_invoked": False,
            },
            "drafting": {
                "latest": latest_draft_artifact(uid, cid),
                "versions": drafts,
                "version_count": len(drafts),
                "human_review_required": True,
            },
            "capabilities": {
                "case_workspace": True,
                "legal_intelligence": True,
                "ask_ai": True,
                "draft": True,
                "final_legal_approval": False,
            },
        }

    def _build_dashboard(self, uid, cid, case, documents, intelligence, drafts, history, *, include_deep_intelligence):
        """Compose a bounded, privacy-safe dashboard from existing case stores."""
        from datetime import date, datetime
        from .. import db
        from ..db import list_case_events, list_case_tasks, get_case_versions

        db.init_case_workspace_tables()
        db.init_case_dates_table()
        db.init_case_reminders_table()
        try:
            from zoneinfo import ZoneInfo
            local_today = datetime.now(ZoneInfo("Asia/Tehran")).date()
        except Exception:
            local_today = date.today()
        today = local_today.isoformat()
        in_14_days = date.fromordinal(local_today.toordinal() + 14).isoformat()
        tasks_all = list_case_tasks(uid, cid, include_done=True, limit=250)
        open_tasks = [x for x in tasks_all if not x.get("done")]
        overdue = [x for x in open_tasks if x.get("due_at") and str(x["due_at"])[:10] < today]
        upcoming_tasks = [x for x in open_tasks if x.get("due_at") and today <= str(x["due_at"])[:10] <= in_14_days]
        next_tasks = sorted(open_tasks, key=lambda x: (not bool(x.get("due_at")), str(x.get("due_at") or "9999"), -int(x.get("id") or 0)))[:5]
        events = list_case_events(uid, cid, limit=12)
        versions = get_case_versions(uid, cid)
        # Every query is scoped by both authenticated owner and case id.
        with db.conn() as conn:
            date_rows = conn.execute("""SELECT d.id,d.date_jalali,d.date_gregorian,d.description,d.source_page,d.created_at,
                    EXISTS(SELECT 1 FROM case_date_reminders r WHERE r.case_date_id=d.id AND r.user_id=? AND r.enabled=1) AS reminder_enabled
                FROM case_important_dates d JOIN cases c ON c.id=d.case_id
                WHERE d.user_id=? AND c.user_id=? AND d.case_id=? AND c.status!='archived'
                ORDER BY d.date_gregorian ASC,d.id ASC LIMIT 100""", (uid,uid,uid,cid)).fetchall()
            people_rows = conn.execute("""SELECT cl.name FROM clients cl JOIN client_case_links l ON l.client_id=cl.id
                JOIN cases c ON c.id=l.case_id WHERE l.user_id=? AND c.user_id=? AND l.case_id=?
                ORDER BY cl.name LIMIT 20""", (uid,uid,cid)).fetchall() if (db._table_exists(conn, "clients") and db._table_exists(conn, "client_case_links")) else []
            note_row = conn.execute("SELECT updated_at FROM case_lawyer_notes WHERE user_id=? AND case_id=?", (uid,cid)).fetchone() if db._table_exists(conn, "case_lawyer_notes") else None
        date_rows = [dict(x) for x in date_rows]
        upcoming_dates = [x for x in date_rows if x.get("date_gregorian") and str(x["date_gregorian"]) >= today][:8]
        clients = [str(x["name"])[:100] for x in people_rows if x["name"]]
        docs_with_text = sum(1 for x in documents if x.get("has_text"))
        docs_without_text = len(documents) - docs_with_text
        summary = intelligence.get("summary") or {}
        chronology = intelligence.get("chronology") or {}
        issues = intelligence.get("issues") or {}
        evidence = intelligence.get("evidence") or {}
        authorities = intelligence.get("authorities") or {}
        claims = evidence.get("claims") or []
        matrix = evidence.get("matrix") or []
        conflicts = chronology.get("conflicts") or []
        timeline_events = chronology.get("events") or []
        issue_items = issues.get("issues") or []
        evidence_gaps = [x for x in matrix if not (x.get("evidence") or [])]
        alerts = []
        def alert(kind, severity, title, message, source_kind, source_id=None, document_id=None, page=None, target=None, score=0, due_date=None):
            alerts.append({"id": f"{kind}:{source_id if source_id is not None else len(alerts)}", "type": kind,
                "severity": severity, "title": title, "message": message,
                "source": {"kind": source_kind, "id": source_id, "document_id": document_id, "page": page},
                "action_label": "بررسی", "action_target": target or source_kind,
                "priority_score": int(score), "due_date": due_date})
        for task in overdue[:12]:
            alert("overdue_task", "high", "کار عقب‌افتاده", str(task.get("title") or "کار پرونده")[:140], "task", task.get("id"), target="tasks", score=100, due_date=task.get("due_at"))
        for task in upcoming_tasks[:8]:
            due = str(task.get("due_at") or "")[:10]
            try:
                days = (date.fromisoformat(due) - local_today).days
            except ValueError:
                days = 14
            score = 92 if days <= 1 else 82 if days <= 3 else 70 if days <= 7 else 58
            alert("upcoming_task", "high" if days <= 3 else "warning", "کار با موعد نزدیک", str(task.get("title") or "کار پرونده")[:140], "task", task.get("id"), target="tasks", score=score, due_date=task.get("due_at"))
        for item in upcoming_dates[:12]:
            if item.get("date_gregorian") and item["date_gregorian"] <= in_14_days:
                due = str(item["date_gregorian"])[:10]
                try:
                    days = (date.fromisoformat(due) - local_today).days
                except ValueError:
                    days = 14
                score = 88 if days <= 1 else 78 if days <= 3 else 66 if days <= 7 else 54
                alert("deadline", "high" if days <= 3 else "warning", "تاریخ استخراج‌شده نزدیک است", str(item.get("description") or "تاریخ مهم")[:140], "case_date", item.get("id"), page=item.get("source_page"), target="timeline", score=score, due_date=due)
        for item in conflicts[:8]:
            alert("timeline_conflict", "warning", "تعارض زمانی نیازمند بررسی", str(item.get("message") or item.get("title") or "تعارض زمانی")[:180], "timeline", item.get("id"), document_id=item.get("document_id"), page=item.get("page"), target="timeline", score=68)
        for item in evidence_gaps[:8]:
            alert("evidence_gap", "info", "ادعای نیازمند بررسی مدرک", str(item.get("claim") or item.get("text") or "برای این ادعا مدرک مرتبطی در ماتریس ثبت نشده است.")[:180], "evidence", item.get("claim_id") or item.get("id"), target="evidence", score=38)
        for doc in documents:
            if not doc.get("has_text"):
                alert("missing_text", "warning", "متن سند در دسترس نیست", str(doc.get("file_name") or "سند")[:140], "document", doc.get("id"), document_id=doc.get("id"), target="documents", score=56)
        unverified = [x for x in (authorities.get("authorities") or []) if x.get("verification_status") != "verified"]
        for item in unverified[:6]:
            alert("unverified_authority", "info", "منبع قانونی نیازمند راستی‌آزمایی", str(item.get("title") or item.get("name") or "استناد نامزد")[:140], "authority", item.get("id"), target="intelligence", score=28)
        # Stable deterministic ordering: urgency first, then nearest due date, then stable id.
        alerts.sort(key=lambda a: (-a["priority_score"], str(a.get("due_date") or "9999-99-99"), a["id"]))
        alerts = alerts[:20]
        for item in alerts:
            item["priority_band"] = "urgent" if item["priority_score"] >= 85 else "soon" if item["priority_score"] >= 55 else "review"
        priority_summary = {"urgent": sum(1 for a in alerts if a["priority_band"] == "urgent"),
            "soon": sum(1 for a in alerts if a["priority_band"] == "soon"),
            "review": sum(1 for a in alerts if a["priority_band"] == "review"),
            "top_action": (alerts[0] if alerts else None),
            "method": "deterministic_rules_not_legal_deadline_validation"}
        limitations = ["تاریخ‌های استخراج‌شده لزوماً مهلت قانونی نیستند و باید با سند اصلی تطبیق داده شوند.",
            "خلأ مدرک در ماتریس به معنی نبود مدرک در پرونده نیست.",
            "تعارض‌ها و مسائل استخراج‌شده نشانه بررسی‌اند، نه یافته قضایی.",
            "منابع قانونی نامزد تا زمان بررسی متن رسمی و اعتبار روز، معتبر یا قابل اعمال فرض نمی‌شوند."]
        if not include_deep_intelligence:
            limitations.append("نمای سبک است؛ موتورهای تحلیل عمیق در این درخواست اجرا نشده‌اند.")
        latest_docs = sorted(documents, key=lambda x: str(x.get("created_at") or ""), reverse=True)[:5]
        return {
            "dashboard_contract_version": 1,
            "case": {"id": cid, "name": case.get("file_name") or "", "status": case.get("status"), "stage": case.get("stage"),
                "priority": case.get("priority"), "next_action": case.get("next_action"), "created_at": case.get("created_at"),
                "updated_at": case.get("updated_at"), "archived": case.get("status") == "archived"},
            "people": {"client_names": clients, "count": len(clients)},
            "overview": {"document_count": len(documents), "documents_with_text": docs_with_text, "documents_without_text": docs_without_text,
                "version_count": len(versions), "open_task_count": len(open_tasks), "overdue_task_count": len(overdue),
                "upcoming_task_count": len(upcoming_tasks), "important_date_count": len(date_rows), "recent_event_count": len(events),
                "issue_count": len(issue_items), "claim_count": len(claims), "evidence_gap_count": len(evidence_gaps),
                "timeline_event_count": len(timeline_events), "timeline_conflict_count": len(conflicts)},
            "intelligence": {"summary": summary, "issues_preview": issue_items[:5], "evidence_preview": matrix[:5],
                "timeline_preview": timeline_events[:5], "authorities_summary": authorities.get("counts") or {},
                "guidance_summary": {"sufficient": bool((intelligence.get("guidance") or {}).get("sufficient")), "ai_used": False}},
            "attention": {"alerts": alerts, "basis": "deterministic_local_rules", "confidence": "low", "priority_summary": priority_summary,
                "recommended_next_actions": alerts[:3]},
            "tasks": {"next": [{k: t.get(k) for k in ("id","title","due_at","done","created_at")} for t in next_tasks],
                "overdue": [{k: t.get(k) for k in ("id","title","due_at","created_at")} for t in overdue[:8]], "open_count": len(open_tasks)},
            "dates": {"upcoming": [{k: d.get(k) for k in ("id","date_jalali","date_gregorian","description","source_page","reminder_enabled")} for d in upcoming_dates],
                "reminder_policy_note": "یادآوری تاریخ استخراج‌شده فقط با فعال‌سازی صریح کاربر انجام می‌شود؛ سیاست فعلی یک روز قبل است."},
            "recent_activity": [{k: e.get(k) for k in ("id","event_type","title","created_at")} for e in events],
            "documents": {"latest": [{k: d.get(k) for k in ("id","file_name","page_count","created_at","text_chars","has_text")} for d in latest_docs],
                "quality": {"with_text": docs_with_text, "without_text": docs_without_text}},
            "drafting": {"latest": ({k: drafts[0].get(k) for k in ("id", "version_no", "status", "brief_type", "created_at", "updated_at")} if drafts else None), "version_count": len(drafts), "human_review_required": True},
            "ai": {"history_count": len(history), "latest_activity_at": (history[0].get("created_at") if history else None), "user_triggered": True, "auto_invoked": False},
            "lawyer_note": {"has_note": bool(note_row), "updated_at": (note_row["updated_at"] if note_row else None)},
            "data_quality": {"coverage": {"documents": len(documents), "tasks": len(tasks_all), "dates": len(date_rows), "events": len(events), "deep_intelligence_computed": bool(include_deep_intelligence)},
                "limitations": limitations, "generated_at": db.now_iso()},
            "navigation": {"documents": f"/api/v1/cases/{cid}/documents", "timeline": f"/api/v1/cases/{cid}/timeline",
                "evidence": f"/api/v1/cases/{cid}/evidence", "tasks": f"/api/v1/cases/{cid}/tasks",
                "ai": f"/api/v1/cases/{cid}/ai/history", "drafts": f"/api/v1/cases/{cid}/drafts"},
        }

    def run_draft(self, user_id: int, case_id: int, *, brief_type: str = "لایحه دفاعیه",
                  answers: Optional[Dict[str, Any]] = None,
                  deferred: Optional[set[str]] = None,
                  allow_incomplete: bool = False) -> Dict[str, Any]:
        uid, cid = _uid(user_id), _cid(case_id)
        return run_drafting_workflow(
            uid, cid, brief_type=brief_type, answers=answers or {},
            deferred=deferred or set(), allow_incomplete=allow_incomplete,
        )


    def ask_ai(self, user_id: int, case_id: int, question: str, *, context_mode: str = "full") -> Dict[str, Any]:
        """Ask AI with a deterministic, case-grounded context and metered entitlement.

        The Mini App never sends the raw case directly. This method assembles a
        bounded context from the canonical case/document/intelligence layers,
        reserves one AI entitlement before the external call, commits on success
        and refunds on failure.
        """
        uid, cid = _uid(user_id), _cid(case_id)
        question = str(question or "").strip()
        if not question:
            raise ProductCaseError("سؤال خالی است.")
        if len(question) > 4000:
            raise ProductCaseError("سؤال بیش از حد مجاز است.")

        from .cases import CaseService
        case = CaseService().get(uid, cid)
        if not case:
            raise ProductCaseError("پرونده پیدا نشد.")
        if case.get("status") == "archived":
            raise ProductCaseError("پرسش AI روی پرونده بایگانی‌شده مجاز نیست.")

        text = get_case_text(uid, cid) or ""
        mode = str(context_mode or "full").strip().lower()
        if mode not in {"full", "intelligence", "documents"}:
            mode = "full"

        # The AI helper caps case context at 12,000 characters. Build a balanced,
        # explicit budget here so document text is not silently pushed out by
        # large JSON intelligence sections in the default "full" mode.
        context_budget = max(500, min(11000, int(AI_TEXT_MAX_CHARS) - 500))
        case_label = str(case.get("file_name") or case.get("name") or "بدون نام")[:180]
        metadata = (
            f"نام پرونده: {case_label}\n"
            f"مرحله: {case.get('stage') or 'نامشخص'} | اولویت: {case.get('priority') or 'نامشخص'}"
        )
        parts = [metadata[:400]]
        context_coverage_note = ""
        document_text_included = False
        document_text_sampled = False

        selection_audit = {}

        def add_section(title, value, limit):
            value = str(value or "").strip()
            if not value:
                return
            clipped = len(value) > limit
            excerpt = value[:limit]
            parts.append(f"{title}:\n{excerpt}" + ("\n[ادامه این بخش برای کنترل حجم ارسال نشده است]" if clipped else ""))

        def add_records(title, records, *, max_items, char_budget):
            # Reserve space for the heading and never slice serialized JSON.
            selected, audit = select_records(records, question, max_items=max_items, char_budget=max(100, char_budget - len(title) - 12))
            selection_audit[title] = audit
            if selected:
                encoded = json.dumps(selected, ensure_ascii=False)
                if len(encoded) + len(title) + 2 <= char_budget:
                    parts.append(f"{title}:\n{encoded}")
                else:
                    selection_audit[title]["omitted_for_budget"] = True

        if mode in {"full", "intelligence"}:
            # Cache deterministic case intelligence briefly. The fingerprint
            # includes current document text hashes and case-event changes;
            # question-specific record/page selection below remains fresh.
            from .case_context_cache import case_fingerprint, get_or_build
            from ..db import list_case_events
            current_docs = get_case_documents(uid, cid)
            current_events = list_case_events(uid, cid, limit=500)
            fingerprint = case_fingerprint(case=case, documents=current_docs, events=current_events)

            def build_intelligence_snapshot():
                cached_chronology = build_case_chronology(uid, cid, include_undated=True)
                cached_issues = build_case_issues(uid, cid)
                cached_evidence = build_evidence_matrix(uid, cid)
                cached_guidance = build_case_guidance(text) if text.strip() else {"sufficient": False}
                cached_authorities = build_case_authorities(uid, cid)
                cached_summary = _build_intelligence_summary(
                    cached_chronology, cached_issues, cached_evidence, {}, {}, cached_guidance, compact=True
                )
                return {"chronology": cached_chronology, "issues": cached_issues,
                        "evidence": cached_evidence, "guidance": cached_guidance,
                        "authorities": cached_authorities, "summary": cached_summary}

            intelligence, cache_hit = get_or_build(uid, cid, fingerprint, build_intelligence_snapshot)
            chronology = intelligence["chronology"]
            issues = intelligence["issues"]
            evidence = intelligence["evidence"]
            guidance = intelligence["guidance"]
            authorities = intelligence["authorities"]
            summary = intelligence["summary"]
            selection_audit["case_context_cache"] = {
                "status": "hit" if cache_hit else "rebuilt",
                "scope": "current_user_and_case_only",
                "ttl_seconds": 120,
                "storage": "process_memory_only",
                "raw_documents_persisted_by_cache": False,
            }

            if mode == "full":
                budgets = {"summary": 1100, "timeline": 1050, "issues": 850,
                           "evidence": 1250, "authorities": 850}
            else:
                budgets = {"summary": 1600, "timeline": 1700, "issues": 1450,
                           "evidence": 1900, "authorities": 1500}

            # Select complete source-backed records against the explicit question;
            # never truncate JSON mid-record. Weak lexical matches fall back to
            # the existing deterministic leading records.
            add_section("خلاصه هوشمندی پرونده", json.dumps(summary, ensure_ascii=False), budgets["summary"])
            add_records("Timeline / رویدادهای مرتبط", chronology.get("events") or [], max_items=12, char_budget=budgets["timeline"])
            add_records("Timeline / تعارض‌های مرتبط", chronology.get("conflicts") or [], max_items=8, char_budget=max(300, budgets["timeline"] // 2))
            add_records("Issues", issues.get("issues") or [], max_items=10, char_budget=budgets["issues"])
            add_records("Evidence / ادعاها", evidence.get("claims") or [], max_items=10, char_budget=max(300, budgets["evidence"] // 2))
            add_records("Evidence / ماتریس", evidence.get("matrix") or [], max_items=10, char_budget=max(300, budgets["evidence"] // 2))
            add_records("نامزدهای منبع حقوقی محلی؛ نیازمند راستی‌آزمایی", authorities.get("authorities") or [], max_items=8, char_budget=budgets["authorities"])

        if mode in {"full", "documents"}:
            # Keep page labels and sample the beginning, middle and end rather
            # than taking only the beginning of a long case file.
            fixed_size = sum(len(part) for part in parts) + 320
            document_budget = max(300, context_budget - fixed_size)
            focused_text, page_selection = select_document_pages(text, question, max_pages=6)
            if page_selection.get("strategy") == "question_relevance_pages":
                sampled_text, was_sampled = _sample_case_text(focused_text, document_budget)
                selection_audit["document_pages"] = page_selection
                selection_audit["document_pages"]["sampled_within_budget"] = bool(was_sampled)
            else:
                sampled_text, was_sampled = _sample_case_text(text, document_budget)
                selection_audit["document_pages"] = page_selection
            document_text_included = bool(text.strip())
            document_text_sampled = bool(was_sampled or page_selection.get("strategy") == "question_relevance_pages")
            if not text.strip():
                sampled_text = "متن استخراج‌شده‌ای برای این پرونده موجود نیست."
                context_coverage_note = "متن استخراج‌شده‌ای در پرونده پیدا نشد؛ ابتدا سند اضافه یا OCR را تکمیل کنید."
            elif page_selection.get("strategy") == "question_relevance_pages":
                context_coverage_note = "صفحات دارای تطبیق واژگانی با سؤال برای کاهش حجم انتخاب شده‌اند؛ این انتخاب جست‌وجوی معنایی کامل نیست و بررسی همه صفحات محسوب نمی‌شود. صفحات انتخاب‌شده: " + ", ".join(str(x) for x in page_selection.get("selected_pages", []))
            elif was_sampled:
                context_coverage_note = "برای کنترل حجم، فقط گزیده‌ای از ابتدا، میانه و انتهای متن اسناد ارسال شده است؛ این پاسخ بررسی کامل همه متن نیست."
            else:
                context_coverage_note = "متن استخراج‌شده اسناد در محدوده مجاز به AI ارسال شده است."
            add_section("متن اسناد پرونده با برچسب صفحات", sampled_text, document_budget)
            if context_coverage_note:
                parts.append("پوشش اسناد: " + context_coverage_note)
        elif mode == "intelligence":
            context_coverage_note = "این حالت از داده‌های ساختاریافته Timeline و Evidence و تحلیل محلی استفاده می‌کند؛ متن خام اسناد مستقیماً در context ارسال نشده است."
            parts.append("پوشش context: " + context_coverage_note)

        context = "\n\n---\n\n".join(parts)
        if len(context) > context_budget:
            marker = "\n[بخش‌هایی از context برای کنترل حجم حذف شده‌اند]"
            context = context[:max(0, context_budget - len(marker))] + marker

        reservation_service = EntitlementService()
        ok, reservation = reservation_service.reserve(
            uid, "ai_question", {"case_id": cid, "context_mode": mode}
        )
        if not ok:
            raise ProductCaseError(
                "اعتبار یا سهمیه سؤال AI کافی نیست."
                if reservation == "insufficient"
                else str(reservation)
            )
        try:
            answer = ask_ai_question(
                question,
                case_summary=context,
                standard_prompt=(
                    "این پرسش داخل پرونده مطرح شده است. پاسخ را فقط بر اساس context پرونده بده. "
                    "اگر به سند یا صفحه مشخصی تکیه می‌کنی، فقط وقتی شماره صفحه در متن زمینه وجود دارد با عبارت «منبع: [صفحه N]» ارجاع بده. "
                    "منابع حقوقی موجود صرفاً نامزدهای بازیابی‌شده‌اند؛ فقط عنوان/شماره‌ای را ذکر کن که صریحاً در زمینه آمده و وضعیت بررسی آن را روشن کن. "
                    "بین واقعیت ثبت‌شده، ادعای طرف، استنباط و اطلاعات ناکافی تفاوت بگذار. "
                    "هیچ ماده قانون، رأی، وضعیت اعتبار یا واقعیت جدیدی اختراع نکن. اگر منبع قابل اتکا نیست، صریحاً بگو."
                ),
                preference_uid=uid,
            )
            if not reservation_service.commit(uid, reservation):
                raise RuntimeError("ثبت مصرف سهمیه AI انجام نشد.")
        except Exception:
            reservation_service.refund(uid, reservation)
            raise

        add_case_ai_exchange(uid, cid, question, answer, context_mode=mode)
        citation_audit = _audit_answer_page_citations(answer, text)
        return {
            "question": question,
            "answer": answer,
            "context_mode": mode,
            "case_id": cid,
            "metered": True,
            "human_review_required": True,
            "citation_audit": citation_audit,
            "context_coverage": {
                "mode": mode,
                "note": context_coverage_note or "context ساختاریافته پرونده برای پرسش AI آماده شد.",
                "document_text_included": document_text_included,
                "document_text_sampled": document_text_sampled,
                "selection_audit": selection_audit,
            },
            "legal_sources_are_candidates": True,
        }

    def ai_history(self, user_id: int, case_id: int, limit: int = 5):
        uid, cid = _uid(user_id), _cid(case_id)
        # Access check happens before exposing history.
        from .cases import CaseService
        if not CaseService().get(uid, cid):
            raise ProductCaseError("پرونده پیدا نشد.")
        return get_case_ai_history(uid, cid, max(1, min(int(limit), 10)))
