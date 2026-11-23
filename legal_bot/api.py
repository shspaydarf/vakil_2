"""Small, dependency-light HTTP API for the future Telegram Mini App.

API-01 intentionally uses only Python's standard library so the project can run
on the existing Replit environment without adding a web framework yet.
Authentication is Telegram Mini App ``initData`` in production; a development
header is available only when explicitly enabled.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import time
import uuid
from email import policy
from email.parser import BytesParser
import tempfile
from urllib.request import Request, urlopen
from urllib.error import URLError
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from .config import (
    BOT_TOKEN, MINIAPP_URL, MAX_FILE_MB, MAX_CASE_ADDITION_FILES,
    MAX_UPLOAD_REQUEST_MB, AI_ENABLED, AI_EXTERNAL_DATA_CONSENT, DEEPSEEK_API_KEY,
    ADMIN_TELEGRAM_IDS, ADMIN_CARD_NUMBER, ADMIN_CARD_HOLDER, SUBSCRIPTION_PRICE_TEXT,
)
from .db import get_user, init_db, v193_upgrade, v20_upgrade, v67_upgrade, init_case_workspace_tables, init_case_dates_table, init_case_reminders_table, init_drafting_workflow_tables, init_case_workflow_agent_tables
from .core.cases import CaseService, CaseValidationError
from .core.product import ProductCaseError, ProductCaseService
from .core.documents import DocumentService, DocumentValidationError
from .timeline_engine import build_case_chronology
from .evidence_engine import build_evidence_matrix
from . import db
from . import quiz as student_quiz
from .drafting_artifacts import init_drafting_artifact_tables, get_draft_artifact, latest_draft_artifact, list_draft_artifacts, record_draft_review, list_draft_reviews, list_work_products, set_work_product_saved, init_work_product_bookmarks
from .analysis import search_case_documents
from .unified_search import search_user_workspace
from .cross_document_analysis import analyze_case_documents
from .review_tables import build_review_table
from .contract_playbooks import list_contract_playbooks, build_playbook_checklist
from .ai import review_contract_risks
from .core.ai_entitlement import AIEntitlementService
from .files import extract_with_diagnostics
from .tax_assistant import build_tax_screen_guide
from .calendar_dates import parse_jalali, parse_gregorian, jalali_to_gregorian, gregorian_to_jalali
from .case_workflow_agent import create_case_workflow, approve_step, run_approved_step, workflow_summary
from .lawyer_preferences import get_schema as get_lawyer_preference_schema, normalize_preferences, suggest_from_feedback
from . import lawyer_preference_service as lawyer_pref_service
from .lawyer_preference_store import ProfileVersionConflict, ProfileNotFound, ProfileVersionNotFound, ConfirmationRequired, PreferencePrivacyError, ProfileIntegrityError
from .lawyer_library import list_lawyer_library, create_lawyer_library_item, update_lawyer_library_item, delete_lawyer_library_item, init_lawyer_library
from .drafting_workflow import load_workflow_state, preflight_v150
from .workflow_templates import list_workflow_templates
from .ai_usage import usage_report, init_ai_usage_tables
from .lawyer_workflows import (list_lawyer_workflows, create_lawyer_workflow, update_lawyer_workflow, delete_lawyer_workflow, start_workflow_run, list_workflow_runs, update_workflow_run, init_lawyer_workflows)
from .laws import search as legal_law_search, get_source_record as legal_source_record, related_sources as legal_related_sources
from .glossary import lookup as glossary_lookup
from .calculator_data import MAHR_ANNUAL_INDEX, MAHR_PROVISIONAL_YEARS
from .calculators import (parse_amount as calculator_parse_amount, mahr_value as calculator_mahr_value,
    diyah_percentage as calculator_diyah_percentage, delay_damage as calculator_delay_damage,
    court_fee as calculator_court_fee, lawyer_fee_financial as calculator_lawyer_fee,
    lawyer_fee_split as calculator_lawyer_fee_split, parse_iso_date as calculator_parse_iso_date,
    add_calendar_days as calculator_add_days, DIYA_FULL_1405_NORMAL, DIYA_FULL_1405_HARAM,
    HEAD_WOUND_PCTS, COLOR_PCTS, CALC_SOURCE_NOTES, alcohol_article_702_fine)
from .check_assistant import build_check_guide, HOLDER_TOPICS, DRAWER_TOPICS
from .family_assistant import build_family_guide, CREDITOR_TOPICS, DEBTOR_TOPICS
from .ejare_assistant import build_ejare_guide, TENANT_TOPICS, LANDLORD_TOPICS
from .shora_assistant import build_shora_guide, TOPICS as SHORA_TOPICS, AMOUNT_BANDS as SHORA_AMOUNT_BANDS, HAS_DOC as SHORA_HAS_DOC
from .tax_assistant import build_tax_guide, ACTIVITIES as TAX_ACTIVITIES, TASKS as TAX_TASKS, INCOME_BANDS as TAX_INCOME_BANDS
from .contract_tree import interactive_contract_start, interactive_contract_step
from .claims_tree import interactive_claims_start, interactive_claims_step
from .property_tree import interactive_property_start, interactive_property_step
from .check_tree import interactive_check_start, interactive_check_step
from .ejare_tree import interactive_lease_start, interactive_lease_step

log = logging.getLogger("legal_bot.api")

API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8080"))
API_DEV_MODE = os.getenv("API_DEV_MODE", "0").lower() in {"1", "true", "yes", "on"}
API_DEV_USER_ID = int(os.getenv("API_DEV_USER_ID", "0") or 0)
API_MAX_AUTH_AGE = max(60, int(os.getenv("API_MAX_AUTH_AGE", "86400")))
API_ALLOWED_ORIGIN = os.getenv("API_ALLOWED_ORIGIN", "*").strip() or "*"
API_ENV = os.getenv("API_ENV", "development").strip().lower()
API_VERSION = "1"
API_RATE_LIMIT_WINDOW = max(1, int(os.getenv("API_RATE_LIMIT_WINDOW", "60")))
API_RATE_LIMIT_REQUESTS = max(10, int(os.getenv("API_RATE_LIMIT_REQUESTS", "120")))
_RATE_LIMIT_LOCK = __import__("threading").Lock()
_RATE_LIMIT_BUCKETS = {}
_GUIDED_TREE_LOCK = __import__("threading").Lock()
_GUIDED_TREE_SESSIONS = {}
_STUDENT_PRACTICE_LOCK = __import__("threading").RLock()
_STUDENT_PRACTICE_SESSIONS = {}
_STUDENT_PRACTICE_TTL = 3600


def _json_default(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _json_bytes(payload):
    return json.dumps(payload, ensure_ascii=False, default=_json_default, separators=(",", ":")).encode("utf-8")


def telegram_user_id_from_init_data(init_data: str, bot_token: str | None = None) -> int:
    """Validate Telegram WebApp initData and return the authenticated user id."""
    if not init_data:
        raise ValueError("initData خالی است.")
    token = bot_token or BOT_TOKEN
    if not token:
        raise ValueError("BOT_TOKEN تنظیم نشده است.")

    pairs = parse_qs(init_data, keep_blank_values=True)
    received_hash = (pairs.pop("hash", [""])[0] or "").strip().lower()
    if not received_hash or not re.fullmatch(r"[0-9a-f]{64}", received_hash):
        raise ValueError("امضای Telegram نامعتبر است.")

    data_check_string = "\n".join(f"{key}={pairs[key][0]}" for key in sorted(pairs))
    secret_key = hmac.new(b"WebAppData", token.encode("utf-8"), hashlib.sha256).digest()
    expected = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        raise ValueError("اعتبارسنجی Telegram ناموفق بود.")

    try:
        auth_date = int(pairs.get("auth_date", ["0"])[0])
    except ValueError:
        auth_date = 0
    now = time.time()
    if auth_date <= 0 or auth_date > now + 60 or now - auth_date > API_MAX_AUTH_AGE:
        raise ValueError("initData منقضی شده است.")

    try:
        user = json.loads(pairs.get("user", ["{}"]) [0])
        uid = int(user["id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise ValueError("اطلاعات کاربر Telegram نامعتبر است.")
    if uid <= 0:
        raise ValueError("شناسه کاربر نامعتبر است.")
    return uid


def _rate_limit_key(handler):
    # Prefer authenticated Telegram identity, otherwise fall back to peer IP.
    init_data = handler.headers.get("X-Telegram-Init-Data", "").strip()
    if init_data:
        try:
            return "u:" + str(telegram_user_id_from_init_data(init_data))
        except Exception:
            pass
    return "ip:" + str(handler.client_address[0] if handler.client_address else "unknown")


def _check_rate_limit(handler):
    now = time.monotonic()
    key = _rate_limit_key(handler)
    with _RATE_LIMIT_LOCK:
        bucket = _RATE_LIMIT_BUCKETS.setdefault(key, [])
        cutoff = now - API_RATE_LIMIT_WINDOW
        while bucket and bucket[0] <= cutoff:
            bucket.pop(0)
        if len(bucket) >= API_RATE_LIMIT_REQUESTS:
            retry_after = max(1, int(bucket[0] + API_RATE_LIMIT_WINDOW - now))
            raise RuntimeError(f"RATE_LIMIT:{retry_after}")
        bucket.append(now)
        # Avoid unbounded memory growth from one-off IPs.
        if len(_RATE_LIMIT_BUCKETS) > 5000:
            oldest = min(_RATE_LIMIT_BUCKETS, key=lambda k: _RATE_LIMIT_BUCKETS[k][-1] if _RATE_LIMIT_BUCKETS[k] else 0)
            _RATE_LIMIT_BUCKETS.pop(oldest, None)


def _auth_user(headers) -> int:
    init_data = headers.get("X-Telegram-Init-Data", "").strip()
    if init_data:
        return telegram_user_id_from_init_data(init_data)

    # Development-only escape hatch. Never enabled by default and never accepts
    # arbitrary user IDs in production.
    if API_DEV_MODE and API_DEV_USER_ID > 0:
        value = headers.get("X-Dev-User-Id", "").strip()
        if value and int(value) == API_DEV_USER_ID:
            return API_DEV_USER_ID
    raise PermissionError("احراز هویت Telegram لازم است.")


class APIHandler(BaseHTTPRequestHandler):
    server_version = "LegalBotAPI/1.0"

    def log_message(self, fmt, *args):
        log.info("%s - %s", self.address_string(), fmt % args)

    def _headers(self, status=200, content_type="application/json; charset=utf-8", retry_after=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        if API_ALLOWED_ORIGIN != "*":
            self.send_header("Access-Control-Allow-Origin", API_ALLOWED_ORIGIN)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Telegram-Init-Data, X-Dev-User-Id, X-AI-Usage-Admin-Token")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if API_ENV in {"prod", "production"}:
            self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if retry_after is not None:
            self.send_header("Retry-After", str(retry_after))
        self.end_headers()

    def _send(self, status, payload, retry_after=None):
        body = _json_bytes(payload)
        self._headers(status, retry_after=retry_after)
        self.wfile.write(body)

    def _error(self, status, code, message):
        self._send(status, {"ok": False, "error": {"code": code, "message": message}})

    def _student_practice_catalog(self, uid):
        if not get_user(uid):
            return self._error(404, "user_not_found", "ابتدا در بات ثبت‌نام کنید و سپس وارد تمرین دانشجویی شوید.")
        query = parse_qs(urlparse(self.path).query)
        level_id = (query.get("level", [""])[0] or "").strip()
        levels = student_quiz.list_levels()
        courses = student_quiz.list_courses(level_id) if level_id else []
        return self._send(200, {"ok": True, "data": {
            "levels": levels, "courses": courses,
            "essay_categories": student_quiz.list_essay_categories(),
            "mcq_disclaimer": student_quiz.disclaimer(),
            "essay_disclaimer": student_quiz.essay_disclaimer(),
        }})

    def _student_practice_action(self, uid, action, data):
        if not get_user(uid):
            return self._error(404, "user_not_found", "ابتدا در بات ثبت‌نام کنید و سپس وارد تمرین دانشجویی شوید.")
        now = time.time()
        with _STUDENT_PRACTICE_LOCK:
            for sid, state in list(_STUDENT_PRACTICE_SESSIONS.items()):
                if now - state.get("updated_at", now) > _STUDENT_PRACTICE_TTL:
                    _STUDENT_PRACTICE_SESSIONS.pop(sid, None)

            if action == "start":
                mode = str(data.get("mode") or "").strip().lower()
                if mode == "mcq":
                    course_id = str(data.get("course_id") or "").strip()
                    if not course_id or course_id not in {c["id"] for level in student_quiz.list_levels() for c in student_quiz.list_courses(level["id"])}:
                        raise ValueError("درس انتخاب‌شده معتبر نیست.")
                    questions, title = student_quiz.get_course_questions(course_id, limit=10, shuffle=True)
                    if not questions:
                        raise ValueError("برای این درس سؤال ثبت نشده است.")
                    state = {"uid": uid, "mode": mode, "title": title, "items": questions,
                             "index": 0, "correct": 0, "answered": False, "updated_at": now}
                elif mode == "essay":
                    category_id = str(data.get("category_id") or "").strip()
                    if category_id not in {c["id"] for c in student_quiz.list_essay_categories()}:
                        raise ValueError("دسته تشریحی انتخاب‌شده معتبر نیست.")
                    items = student_quiz.get_essay_items(category_id, limit=5, shuffle=True)
                    if not items:
                        raise ValueError("برای این دسته سؤال تشریحی ثبت نشده است.")
                    cats = {c["id"]: c["title"] for c in student_quiz.list_essay_categories()}
                    state = {"uid": uid, "mode": mode, "title": cats.get(category_id, category_id),
                             "items": items, "index": 0, "sample_shown": False, "updated_at": now}
                else:
                    raise ValueError("نوع تمرین معتبر نیست.")
                sid = uuid.uuid4().hex
                _STUDENT_PRACTICE_SESSIONS[sid] = state
                return self._send(201, {"ok": True, "data": self._student_practice_current(sid, state)})

            sid = str(data.get("session_id") or "").strip()
            state = _STUDENT_PRACTICE_SESSIONS.get(sid)
            if not sid or not state or state.get("uid") != uid:
                raise ValueError("نشست تمرین پیدا نشد یا منقضی شده است. یک تمرین تازه شروع کنید.")
            state["updated_at"] = now
            idx = int(state.get("index", 0))
            items = state.get("items") or []
            if idx >= len(items):
                raise ValueError("این تمرین به پایان رسیده است.")
            item = items[idx]
            expected_question_token = f"{sid}:{idx}"
            if str(data.get("question_token") or "") != expected_question_token:
                raise ValueError("این درخواست مربوط به سؤال قبلی است. سؤال فعلی را دوباره باز کنید.")

            if action == "answer":
                if state.get("mode") != "mcq":
                    raise ValueError("این نشست آزمون چهارگزینه‌ای نیست.")
                if state.get("answered"):
                    raise ValueError("پاسخ این سؤال قبلاً ثبت شده است.")
                try:
                    choice = int(data.get("choice"))
                except (TypeError, ValueError):
                    raise ValueError("گزینه پاسخ معتبر نیست.")
                if choice not in range(4) or choice >= len(item.get("options") or []):
                    raise ValueError("گزینه پاسخ معتبر نیست.")
                ok, feedback = student_quiz.check_answer(item, choice)
                state["answered"] = True
                if ok:
                    state["correct"] = int(state.get("correct", 0)) + 1
                state["index"] = idx + 1
                state["answered"] = False
                if state["index"] >= len(items):
                    result = {"finished": True, "feedback": feedback, "correct": state["correct"],
                              "total": len(items), "title": state.get("title"),
                              "disclaimer": student_quiz.disclaimer()}
                    _STUDENT_PRACTICE_SESSIONS.pop(sid, None)
                    return self._send(200, {"ok": True, "data": result})
                return self._send(200, {"ok": True, "data": {
                    "finished": False, "feedback": feedback, "correct": state["correct"],
                    "total": len(items), "question": self._student_practice_question(items[state["index"]], state["index"], len(items), sid)
                }})

            if action == "essay-sample":
                if state.get("mode") != "essay":
                    raise ValueError("این نشست تشریحی نیست.")
                state["sample_shown"] = True
                return self._send(200, {"ok": True, "data": {
                    "sample": str(item.get("sample") or "پاسخ نمونه برای این سؤال ثبت نشده است."),
                    "index": idx + 1, "total": len(items), "title": state.get("title"),
                    "disclaimer": student_quiz.essay_disclaimer()
                }})

            if action == "essay-next":
                if state.get("mode") != "essay":
                    raise ValueError("این نشست تشریحی نیست.")
                state["index"] = idx + 1
                state["sample_shown"] = False
                if state["index"] >= len(items):
                    _STUDENT_PRACTICE_SESSIONS.pop(sid, None)
                    return self._send(200, {"ok": True, "data": {"finished": True, "title": state.get("title"),
                        "total": len(items), "disclaimer": student_quiz.essay_disclaimer()}})
                return self._send(200, {"ok": True, "data": self._student_practice_current(sid, state)})

            raise ValueError("عملیات تمرین معتبر نیست.")

    @staticmethod
    def _student_practice_question(item, index, total, sid):
        return {"index": index + 1, "total": total, "question_token": f"{sid}:{index}",
                "question": str(item.get("q") or ""),
                "options": [str(x) for x in (item.get("options") or [])[:4]]}

    def _student_practice_current(self, sid, state):
        idx = int(state.get("index", 0)); items = state.get("items") or []
        item = items[idx]
        result = {"session_id": sid, "mode": state.get("mode"), "title": state.get("title"),
                  "index": idx + 1, "total": len(items), "question_token": f"{sid}:{idx}", "question": str(item.get("q") or ""),
                  "disclaimer": student_quiz.disclaimer() if state.get("mode") == "mcq" else student_quiz.essay_disclaimer()}
        if state.get("mode") == "mcq":
            result["options"] = [str(x) for x in (item.get("options") or [])[:4]]
        return result

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 1_000_000:
                raise ValueError("بدنه درخواست نامعتبر یا بیش از حد بزرگ است.")
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("JSON درخواست نامعتبر است.") from exc

    def do_OPTIONS(self):
        self._headers(204)

    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path == "/healthz":
            return self._send(200, {"ok": True, "service": "legalbot-api", "version": API_VERSION})
        if not path.startswith(f"/api/v{API_VERSION}"):
            return self._error(404, "not_found", "مسیر پیدا نشد.")
        try:
            _check_rate_limit(self)
            uid = _auth_user(self.headers)
            if path == f"/api/v{API_VERSION}/me":
                return self._me(uid)
            if path == f"/api/v{API_VERSION}/account":
                return self._account(uid)
            if path == f"/api/v{API_VERSION}/subscription-info":
                return self._subscription_info(uid)
            if path == f"/api/v{API_VERSION}/search":
                return self._unified_search(uid)
            if path == f"/api/v{API_VERSION}/legal-search":
                return self._legal_search(uid)
            if path == f"/api/v{API_VERSION}/legal-search/source":
                return self._legal_source(uid)
            if path == f"/api/v{API_VERSION}/clients":
                return self._clients(uid)
            if path == f"/api/v{API_VERSION}/calculators":
                return self._calculator_catalog(uid)
            if path == f"/api/v{API_VERSION}/contract-playbooks":
                return self._send(200, {"ok": True, "data": {"items": list_contract_playbooks()}})
            if path == f"/api/v{API_VERSION}/important-dates":
                return self._important_dates(uid)
            if path == f"/api/v{API_VERSION}/referrals":
                return self._referrals(uid)
            if path == f"/api/v{API_VERSION}/guides/catalog":
                return self._guide_catalog(uid)
            if path == f"/api/v{API_VERSION}/admin/ai-usage":
                expected=os.getenv("AI_USAGE_ADMIN_TOKEN", "").strip()
                supplied=self.headers.get("X-AI-Usage-Admin-Token", "").strip()
                if not expected or not supplied or not hmac.compare_digest(expected, supplied):
                    return self._error(403, "forbidden", "دسترسی مدیریتی مصرف AI مجاز نیست.")
                q=parse_qs(urlparse(self.path).query)
                try: days=int(q.get("days",["30"])[0])
                except (TypeError,ValueError): days=30
                return self._send(200, {"ok":True,"data":usage_report(days)})
            if path == f"/api/v{API_VERSION}/recent-activity":
                return self._recent_activity(uid)
            if path == f"/api/v{API_VERSION}/calendar":
                return self._calendar(uid)
            if path == f"/api/v{API_VERSION}/saved-documents":
                return self._saved_documents(uid)
            if path == f"/api/v{API_VERSION}/work-products":
                return self._work_products(uid)
            if path == f"/api/v{API_VERSION}/lawyer-library":
                return self._lawyer_library(uid)
            if path == f"/api/v{API_VERSION}/workflow-templates":
                return self._send(200, {"ok": True, "data": {"items": list_workflow_templates()}})
            if path == f"/api/v{API_VERSION}/lawyer-workflows":
                return self._send(200, {"ok": True, "data": {"items": list_lawyer_workflows(uid)}})
            if path == f"/api/v{API_VERSION}/workflow-runs":
                q=parse_qs(urlparse(self.path).query); raw=q.get("case_id",[""])[0]
                cid=int(raw) if raw.isdigit() else None
                return self._send(200, {"ok": True, "data": {"items": list_workflow_runs(uid,cid)}})
            if path == f"/api/v{API_VERSION}/lawyer-preferences/schema":
                return self._lawyer_preferences_schema(uid)
            if path == f"/api/v{API_VERSION}/lawyer-preferences/history":
                return self._lawyer_preferences_history(uid)
            if path == f"/api/v{API_VERSION}/lawyer-preferences/compare":
                q = parse_qs(urlparse(self.path).query)
                payload = {
                    "from_profile_version": q.get("from_version", [None])[0],
                    "to_profile_version": q.get("to_version", [None])[0],
                }
                result = lawyer_pref_service.compare_history(uid, payload)
                return self._send(200, {"ok": True, "data": result})
            if path == f"/api/v{API_VERSION}/services":
                rows = db.list_service_listings(uid, limit=50)
                return self._send(200, {"ok": True, "data": {"items": rows}})
            if path == f"/api/v{API_VERSION}/student-practice/catalog":
                return self._student_practice_catalog(uid)
            m = re.fullmatch(rf"/api/v{API_VERSION}/clients/(\d+)", path)
            if m:
                return self._client_detail(uid, int(m.group(1)))
            m = re.fullmatch(rf"/api/v{API_VERSION}/cases/(\d+)/tasks", path)
            if m:
                return self._case_tasks(uid, int(m.group(1)))
            m = re.fullmatch(rf"/api/v{API_VERSION}/cases/(\d+)/note", path)
            if m:
                return self._case_note(uid, int(m.group(1)))
            if path == f"/api/v{API_VERSION}/cases":
                return self._cases(uid)
            m = re.fullmatch(rf"/api/v{API_VERSION}/cases/(\d+)/workspace", path)
            if m:
                return self._workspace(uid, int(m.group(1)))
            m = re.fullmatch(rf"/api/v{API_VERSION}/cases/(\d+)/documents", path)
            if m:
                return self._documents(uid, int(m.group(1)))
            m = re.fullmatch(rf"/api/v{API_VERSION}/cases/(\d+)/search", path)
            if m:
                return self._search_case_documents(uid, int(m.group(1)))
            m = re.fullmatch(rf"/api/v{API_VERSION}/cases/(\d+)/document-analysis", path)
            if m:
                return self._analyze_case_documents(uid, int(m.group(1)))
            m = re.fullmatch(rf"/api/v{API_VERSION}/cases/(\d+)/workflow-agent", path)
            if m:
                return self._get_case_workflow_agent(uid, int(m.group(1)))
            m = re.fullmatch(rf"/api/v{API_VERSION}/cases/(\d+)/timeline", path)
            if m:
                return self._timeline(uid, int(m.group(1)))
            m = re.fullmatch(rf"/api/v{API_VERSION}/cases/(\d+)/evidence", path)
            if m:
                return self._evidence(uid, int(m.group(1)))
            m = re.fullmatch(rf"/api/v{API_VERSION}/cases/(\d+)/intelligence", path)
            if m:
                return self._intelligence(uid, int(m.group(1)))
            m = re.fullmatch(rf"/api/v{API_VERSION}/cases/(\d+)/draft-intake", path)
            if m:
                return self._draft_intake(uid, int(m.group(1)))
            m = re.fullmatch(rf"/api/v{API_VERSION}/cases/(\d+)/drafts", path)
            if m:
                return self._drafts(uid, int(m.group(1)))
            m = re.fullmatch(rf"/api/v{API_VERSION}/cases/(\d+)/drafts/([^/]+)/reviews", path)
            if m:
                return self._draft_reviews(uid, int(m.group(1)), unquote(m.group(2)))
            m = re.fullmatch(rf"/api/v{API_VERSION}/cases/(\d+)/drafts/([^/]+)", path)
            if m:
                return self._draft_artifact(uid, int(m.group(1)), unquote(m.group(2)))
            m = re.fullmatch(rf"/api/v{API_VERSION}/cases/(\d+)/ai-history", path)
            if m:
                return self._ai_history(uid, int(m.group(1)))
            return self._error(404, "not_found", "مسیر پیدا نشد.")
        except ProfileNotFound as exc:
            return self._error(404, "preference_profile_not_found", str(exc))
        except ProfileVersionNotFound as exc:
            return self._error(404, "preference_version_not_found", str(exc))
        except ConfirmationRequired as exc:
            return self._error(400, "confirmation_required", str(exc))
        except ProfileVersionConflict:
            return self._error(409, "preference_version_conflict", "ترجیحات در نشست دیگری تغییر کرده‌اند. فرم را تازه‌سازی کنید و دوباره بررسی کنید.")
        except ProfileIntegrityError:
            return self._error(409, "preference_integrity_conflict", "سوابق ترجیحات با پروفایل فعلی سازگار نیست؛ ذخیره متوقف شد.")
        except RuntimeError as exc:
            if str(exc).startswith("RATE_LIMIT:"):
                retry = int(str(exc).split(":", 1)[1])
                self._send(429, {"ok": False, "error": {"code": "rate_limited", "message": "تعداد درخواست‌ها بیش از حد مجاز است."}}, retry_after=retry)
                return
            raise
        except PermissionError as exc:
            return self._error(401, "unauthorized", str(exc))
        except (CaseValidationError, ProductCaseError, DocumentValidationError, ValueError) as exc:
            return self._error(400, "bad_request", str(exc))
        except Exception:
            log.exception("GET API failure")
            return self._error(500, "internal_error", "خطای داخلی سرور.")

    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if not path.startswith(f"/api/v{API_VERSION}"):
            return self._error(404, "not_found", "مسیر پیدا نشد.")
        try:
            _check_rate_limit(self)
            uid = _auth_user(self.headers)
            if path == f"/api/v{API_VERSION}/cases":
                data = self._read_json()
                return self._create_case(uid, data)
            if path == f"/api/v{API_VERSION}/services":
                return self._create_service_listing(uid)
            if path == f"/api/v{API_VERSION}/clients":
                return self._create_client(uid, self._read_json())
            if path == f"/api/v{API_VERSION}/feedback":
                return self._create_feedback(uid, self._read_json())
            if path == f"/api/v{API_VERSION}/referrals":
                return self._create_referral_request(uid, self._read_json())
            if path == f"/api/v{API_VERSION}/subscription-receipts":
                return self._submit_subscription_receipt(uid)
            m = re.fullmatch(rf"/api/v{API_VERSION}/referrals/matches/(\d+)", path)
            if m:
                return self._update_referral_match(uid, int(m.group(1)), self._read_json())
            m = re.fullmatch(rf"/api/v{API_VERSION}/student-practice/(start|answer|essay-sample|essay-next)", path)
            if m:
                return self._student_practice_action(uid, m.group(1), self._read_json())
            if path == f"/api/v{API_VERSION}/calculators/run":
                return self._run_calculator(uid, self._read_json())
            if path == f"/api/v{API_VERSION}/tax/screen":
                return self._tax_screen_upload(uid)
            m = re.fullmatch(rf"/api/v{API_VERSION}/important-dates/(\d+)/reminder", path)
            if m:
                return self._set_important_date_reminder(uid, int(m.group(1)), self._read_json())
            m = re.fullmatch(rf"/api/v{API_VERSION}/cases/(\d+)/contract-review", path)
            if m:
                return self._contract_review(uid, int(m.group(1)), self._read_json())
            m = re.fullmatch(rf"/api/v{API_VERSION}/guides/(check|family|ejare|shora|tax)", path)
            if m:
                return self._run_guide(uid, m.group(1), self._read_json())
            m = re.fullmatch(rf"/api/v{API_VERSION}/guided-trees/(contract|claims|property|check|lease)/start", path)
            if m:
                return self._guided_tree_start(uid, m.group(1), self._read_json())
            m = re.fullmatch(rf"/api/v{API_VERSION}/guided-trees/(contract|claims|property|check|lease)/step", path)
            if m:
                return self._guided_tree_step(uid, m.group(1), self._read_json())
            m = re.fullmatch(rf"/api/v{API_VERSION}/clients/(\d+)/cases/(\d+)", path)
            if m:
                return self._link_client_case(uid, int(m.group(1)), int(m.group(2)))
            if path == f"/api/v{API_VERSION}/calendar/tasks":
                return self._create_calendar_task(uid, self._read_json())
            if path == f"/api/v{API_VERSION}/recent-activity":
                return self._record_recent_activity(uid, self._read_json())
            if path == f"/api/v{API_VERSION}/lawyer-library":
                item = create_lawyer_library_item(uid, self._read_json())
                return self._send(201, {"ok": True, "data": {"item": item}})
            if path == f"/api/v{API_VERSION}/lawyer-workflows":
                item = create_lawyer_workflow(uid, self._read_json())
                return self._send(201, {"ok": True, "data": {"item": item}})
            m = re.fullmatch(rf"/api/v{API_VERSION}/cases/(\d+)/workflow-runs", path)
            if m:
                data=self._read_json(); item=start_workflow_run(uid,int(m.group(1)),str(data.get("workflow_id") or ""))
                return self._send(201, {"ok": True, "data": {"run": item}})
            if path == f"/api/v{API_VERSION}/lawyer-preferences/restore":
                return self._lawyer_preferences_restore_action(uid, self._read_json())
            m = re.fullmatch(rf"/api/v{API_VERSION}/lawyer-preferences/(activate|deactivate)", path)
            if m:
                return self._lawyer_preferences_status_action(uid, m.group(1), self._read_json())
            m = re.fullmatch(rf"/api/v{API_VERSION}/lawyer-preferences/(preview|suggest|save)", path)
            if m:
                return self._lawyer_preferences_action(uid, m.group(1), self._read_json())
            m = re.fullmatch(rf"/api/v{API_VERSION}/cases/(\d+)/workflow-agent/(start|approve|run)", path)
            if m:
                return self._case_workflow_agent_action(uid, int(m.group(1)), m.group(2), self._read_json())
            m = re.fullmatch(rf"/api/v{API_VERSION}/cases/(\d+)/tasks", path)
            if m:
                return self._create_case_task(uid, int(m.group(1)), self._read_json())
            m = re.fullmatch(rf"/api/v{API_VERSION}/cases/(\d+)/note", path)
            if m:
                return self._save_case_note(uid, int(m.group(1)), self._read_json())
            m = re.fullmatch(rf"/api/v{API_VERSION}/cases/(\d+)/drafts/([^/]+)/review", path)
            if m:
                data = self._read_json()
                return self._record_draft_review(uid, int(m.group(1)), unquote(m.group(2)), data)
            m = re.fullmatch(rf"/api/v{API_VERSION}/cases/(\d+)/draft", path)
            if m:
                data = self._read_json()
                return self._draft(uid, int(m.group(1)), data)
            m = re.fullmatch(rf"/api/v{API_VERSION}/cases/(\d+)/documents", path)
            if m:
                return self._upload_documents(uid, int(m.group(1)))
            m = re.fullmatch(rf"/api/v{API_VERSION}/cases/(\d+)/ai", path)
            if m:
                data = self._read_json()
                return self._ask_ai(uid, int(m.group(1)), data)
            return self._error(404, "not_found", "مسیر پیدا نشد.")
        except ProfileNotFound as exc:
            return self._error(404, "preference_profile_not_found", str(exc))
        except ProfileVersionNotFound as exc:
            return self._error(404, "preference_version_not_found", str(exc))
        except ConfirmationRequired as exc:
            return self._error(400, "confirmation_required", str(exc))
        except ProfileVersionConflict:
            return self._error(409, "preference_version_conflict", "ترجیحات در نشست دیگری تغییر کرده‌اند. فرم را تازه‌سازی کنید و دوباره بررسی کنید.")
        except ProfileIntegrityError:
            return self._error(409, "preference_integrity_conflict", "سوابق ترجیحات با پروفایل فعلی سازگار نیست؛ ذخیره متوقف شد.")
        except RuntimeError as exc:
            if str(exc).startswith("RATE_LIMIT:"):
                retry = int(str(exc).split(":", 1)[1])
                self._send(429, {"ok": False, "error": {"code": "rate_limited", "message": "تعداد درخواست‌ها بیش از حد مجاز است."}}, retry_after=retry)
                return
            raise
        except PermissionError as exc:
            return self._error(401, "unauthorized", str(exc))
        except (CaseValidationError, ProductCaseError, DocumentValidationError, ValueError) as exc:
            return self._error(400, "bad_request", str(exc))
        except Exception:
            log.exception("POST API failure")
            return self._error(500, "internal_error", "خطای داخلی سرور.")

    def do_PATCH(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if not path.startswith(f"/api/v{API_VERSION}"):
            return self._error(404, "not_found", "مسیر پیدا نشد.")
        try:
            _check_rate_limit(self)
            uid = _auth_user(self.headers)
            m = re.fullmatch(rf"/api/v{API_VERSION}/calendar/tasks/(\d+)", path)
            if m:
                return self._update_calendar_task(uid, int(m.group(1)), self._read_json())
            m = re.fullmatch(rf"/api/v{API_VERSION}/lawyer-library/([^/]+)", path)
            if m:
                item_id = unquote(m.group(1))
                item = update_lawyer_library_item(uid, item_id, self._read_json())
                if not item:
                    return self._error(404, "library_item_not_found", "منبع پیدا نشد یا متعلق به این حساب نیست.")
                return self._send(200, {"ok": True, "data": {"item": item}})
            m = re.fullmatch(rf"/api/v{API_VERSION}/lawyer-workflows/([^/]+)", path)
            if m:
                item=update_lawyer_workflow(uid,unquote(m.group(1)),self._read_json())
                if not item: return self._error(404,"workflow_not_found","گردش‌کار پیدا نشد یا متعلق به این حساب نیست.")
                return self._send(200,{"ok":True,"data":{"item":item}})
            m = re.fullmatch(rf"/api/v{API_VERSION}/workflow-runs/([^/]+)", path)
            if m:
                data=self._read_json(); run=update_workflow_run(uid,unquote(m.group(1)),data.get("completed",[]),data.get("status","active"))
                if not run: return self._error(404,"workflow_run_not_found","اجرای گردش‌کار پیدا نشد یا متعلق به این حساب نیست.")
                return self._send(200,{"ok":True,"data":{"run":run}})
            m = re.fullmatch(rf"/api/v{API_VERSION}/work-products/(ai|draft)/([^/]+)/pin", path)
            if m:
                data = self._read_json()
                if not isinstance(data, dict) or not isinstance(data.get("saved"), bool):
                    raise ValueError("وضعیت نشان‌کردن باید true یا false باشد.")
                if not set_work_product_saved(uid, m.group(1), unquote(m.group(2)), data["saved"]):
                    return self._error(404, "work_product_not_found", "خروجی پیدا نشد یا متعلق به این حساب نیست.")
                return self._send(200, {"ok": True, "data": {"type": m.group(1), "id": unquote(m.group(2)), "saved": data["saved"]}})
            m = re.fullmatch(rf"/api/v{API_VERSION}/cases/(\d+)/tasks/(\d+)", path)
            if m:
                return self._update_case_task(uid, int(m.group(1)), int(m.group(2)), self._read_json())
            m = re.fullmatch(rf"/api/v{API_VERSION}/cases/(\d+)/documents/(\d+)/pin", path)
            if m:
                data = self._read_json()
                if not isinstance(data, dict) or not isinstance(data.get("saved"), bool):
                    raise ValueError("وضعیت نشان‌کردن سند باید true یا false باشد.")
                cid, did = int(m.group(1)), int(m.group(2))
                if not db.set_document_saved(uid, cid, did, data["saved"]):
                    raise CaseValidationError("سند پیدا نشد یا متعلق به این حساب نیست.")
                return self._send(200, {"ok": True, "data": {"case_id": cid, "document_id": did, "saved": data["saved"]}})
            m = re.fullmatch(rf"/api/v{API_VERSION}/cases/(\d+)/pin", path)
            if m:
                data = self._read_json()
                if not isinstance(data, dict) or not isinstance(data.get("pinned"), bool):
                    raise ValueError("وضعیت نشان‌کردن باید true یا false باشد.")
                if not db.set_case_pinned(uid, int(m.group(1)), data["pinned"]):
                    raise CaseValidationError("پرونده پیدا نشد یا متعلق به این حساب نیست.")
                return self._send(200, {"ok": True, "data": {"case_id": int(m.group(1)), "pinned": data["pinned"]}})
            m = re.fullmatch(rf"/api/v{API_VERSION}/services/(\d+)", path)
            if m:
                return self._update_service_listing(uid, int(m.group(1)))
            m = re.fullmatch(rf"/api/v{API_VERSION}/clients/(\d+)", path)
            if m:
                return self._update_client(uid, int(m.group(1)), self._read_json())
            m = re.fullmatch(rf"/api/v{API_VERSION}/cases/(\d+)", path)
            if m:
                return self._update_case(uid, int(m.group(1)), self._read_json())
            m = re.fullmatch(rf"/api/v{API_VERSION}/cases/(\d+)/(archive|restore)", path)
            if m:
                return self._case_action(uid, int(m.group(1)), m.group(2))
            return self._error(404, "not_found", "مسیر پیدا نشد.")
        except RuntimeError as exc:
            if str(exc).startswith("RATE_LIMIT:"):
                retry = int(str(exc).split(":", 1)[1])
                self._send(429, {"ok": False, "error": {"code": "rate_limited", "message": "تعداد درخواست‌ها بیش از حد مجاز است."}}, retry_after=retry)
                return
            raise
        except PermissionError as exc:
            return self._error(401, "unauthorized", str(exc))
        except (CaseValidationError, ProductCaseError, DocumentValidationError, ValueError) as exc:
            return self._error(400, "bad_request", str(exc))
        except Exception:
            log.exception("PATCH API failure")
            return self._error(500, "internal_error", "خطای داخلی سرور.")

    def do_DELETE(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if not path.startswith(f"/api/v{API_VERSION}"):
            return self._error(404, "not_found", "مسیر پیدا نشد.")
        try:
            _check_rate_limit(self)
            uid = _auth_user(self.headers)
            if path == f"/api/v{API_VERSION}/lawyer-preferences/profile":
                data = self._read_json()
                result = lawyer_pref_service.delete_editor_profile(uid, data)
                return self._send(200, {"ok": True, "data": result})
            m = re.fullmatch(rf"/api/v{API_VERSION}/lawyer-library/([^/]+)", path)
            if m:
                item_id = unquote(m.group(1))
                if not delete_lawyer_library_item(uid, item_id):
                    return self._error(404, "library_item_not_found", "منبع پیدا نشد یا متعلق به این حساب نیست.")
                return self._send(200, {"ok": True, "data": {"deleted": True, "id": item_id}})
            m = re.fullmatch(rf"/api/v{API_VERSION}/lawyer-workflows/([^/]+)", path)
            if m:
                item_id=unquote(m.group(1))
                if not delete_lawyer_workflow(uid,item_id): return self._error(404,"workflow_not_found","گردش‌کار پیدا نشد یا متعلق به این حساب نیست.")
                return self._send(200,{"ok":True,"data":{"deleted":True,"id":item_id}})
            m = re.fullmatch(rf"/api/v{API_VERSION}/cases/(\d+)/tasks/(\d+)", path)
            if m:
                cid, tid = int(m.group(1)), int(m.group(2))
                if not db.delete_case_task(uid, tid, case_id=cid):
                    raise CaseValidationError("کار پیدا نشد یا قابل حذف نیست.")
                return self._send(200, {"ok": True, "data": {"deleted": True, "task_id": tid}})
            m = re.fullmatch(rf"/api/v{API_VERSION}/cases/(\d+)/documents/(\d+)", path)
            if m:
                cid, did = int(m.group(1)), int(m.group(2))
                if not DocumentService().delete_registered(uid, cid, did):
                    raise DocumentValidationError("سند پیدا نشد یا حذف نشد.")
                return self._send(200, {"ok": True, "data": {"deleted": True, "document_id": did}})
            m = re.fullmatch(rf"/api/v{API_VERSION}/services/(\d+)", path)
            if m:
                lid=int(m.group(1))
                if not db.delete_service_listing(uid,lid): return self._error(404,"service_not_found","پروفایل خدمت پیدا نشد یا متعلق به این حساب نیست.")
                return self._send(200,{"ok":True,"data":{"deleted":True,"id":lid}})
            m = re.fullmatch(rf"/api/v{API_VERSION}/clients/(\d+)", path)
            if m:
                return self._delete_client(uid, int(m.group(1)))
            m = re.fullmatch(rf"/api/v{API_VERSION}/cases/(\d+)", path)
            if not m:
                return self._error(404, "not_found", "مسیر پیدا نشد.")
            cid = int(m.group(1))
            if not CaseService().delete(uid, cid):
                raise CaseValidationError("پرونده پیدا نشد یا حذف نشد.")
            return self._send(200, {"ok": True, "data": {"deleted": True, "case_id": cid}})
        except RuntimeError as exc:
            if str(exc).startswith("RATE_LIMIT:"):
                retry = int(str(exc).split(":", 1)[1])
                self._send(429, {"ok": False, "error": {"code": "rate_limited", "message": "تعداد درخواست‌ها بیش از حد مجاز است."}}, retry_after=retry)
                return
            raise
        except ProfileNotFound as exc:
            return self._error(404, "preference_profile_not_found", str(exc))
        except ConfirmationRequired as exc:
            return self._error(400, "confirmation_required", str(exc))
        except ProfileVersionConflict:
            return self._error(409, "preference_version_conflict", "ترجیحات در نشست دیگری تغییر کرده‌اند. فرم را تازه‌سازی کنید و دوباره بررسی کنید.")
        except ProfileIntegrityError:
            return self._error(409, "preference_integrity_conflict", "سوابق ترجیحات با پروفایل فعلی سازگار نیست؛ حذف متوقف شد.")
        except PermissionError as exc:
            return self._error(401, "unauthorized", str(exc))
        except (CaseValidationError, ProductCaseError, DocumentValidationError, ValueError) as exc:
            return self._error(400, "bad_request", str(exc))
        except Exception:
            log.exception("DELETE API failure")
            return self._error(500, "internal_error", "خطای داخلی سرور.")

    def _account(self, uid):
        user = get_user(uid)
        if not user:
            return self._error(404, "user_not_found", "کاربر در سیستم پیدا نشد.")
        safe = dict(user)
        for key in ("phone", "phone_hash", "lawyer_code", "password_hash"):
            safe.pop(key, None)
        from .repositories.credits import CreditRepository
        credits = CreditRepository().status(uid) or {}
        subscription = db.subscription_status(uid) or {"active": False}
        return self._send(200, {"ok": True, "data": {"user": safe, "credits": credits, "subscription": subscription, "api_version": API_VERSION}})

    def _case_tasks(self, uid, cid):
        if not CaseService().get(uid, cid):
            raise CaseValidationError("پرونده پیدا نشد.")
        query=parse_qs(urlparse(self.path).query)
        include_done=query.get("done", ["0"])[0].lower() in {"1","true","yes"}
        items=db.list_case_tasks(uid,cid,include_done=include_done,limit=100)
        return self._send(200,{"ok":True,"data":{"items":items,"count":len(items)}})

    def _create_case_task(self, uid, cid, data):
        if not isinstance(data,dict): raise ValueError("بدنه درخواست باید یک شیء JSON باشد.")
        title=str(data.get("title") or "").strip()
        due_at=data.get("due_at")
        if due_at not in (None, ""):
            if not isinstance(due_at, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:T(?:[01]\d|2[0-3]):[0-5]\d)?", due_at):
                raise ValueError("موعد باید به شکل تاریخ معتبر YYYY-MM-DD یا همراه ساعت ثبت شود.")
            from datetime import date
            try: date.fromisoformat(due_at[:10])
            except ValueError as exc: raise ValueError("تاریخ موعد معتبر نیست.") from exc
        else:
            due_at=None
        reminder_days = data.get("reminder_days")
        if reminder_days not in (None, "", 0, 1, 3, 7, "0", "1", "3", "7"):
            raise ValueError("بازه یادآوری باید یکی از ۰، ۱، ۳ یا ۷ روز باشد.")
        reminder_days = int(reminder_days) if reminder_days not in (None, "") else None
        if reminder_days is not None and due_at is None:
            raise ValueError("برای تنظیم یادآوری باید موعد کار مشخص باشد.")
        tid=db.add_case_task(uid,cid,title,due_at=due_at,reminder_days=reminder_days)
        if not tid: raise CaseValidationError("کار ایجاد نشد یا پرونده قابل ویرایش نیست.")
        item=next((x for x in db.list_case_tasks(uid,cid,include_done=True,limit=100) if int(x["id"])==int(tid)),None)
        return self._send(201,{"ok":True,"data":{"task":item}})

    def _update_case_task(self, uid, cid, tid, data):
        if not isinstance(data,dict): raise ValueError("بدنه درخواست باید یک شیء JSON باشد.")
        if "done" not in data or not isinstance(data.get("done"),bool): raise ValueError("فیلد done باید بولی باشد.")
        if not db.set_case_task_done(uid,tid,bool(data["done"]),case_id=cid): raise CaseValidationError("کار پیدا نشد یا قابل تغییر نیست.")
        return self._send(200,{"ok":True,"data":{"task_id":tid,"done":bool(data["done"])}})

    def _case_note(self, uid, cid):
        if not CaseService().get(uid,cid): raise CaseValidationError("پرونده پیدا نشد.")
        return self._send(200,{"ok":True,"data":{"note":db.get_case_lawyer_note(uid,cid)}})

    def _save_case_note(self, uid, cid, data):
        if not isinstance(data,dict): raise ValueError("بدنه درخواست باید یک شیء JSON باشد.")
        text=str(data.get("text") or "").strip()
        if len(text)>40000: raise ValueError("یادداشت بیش از حد طولانی است.")
        case = CaseService().get(uid, cid)
        if not case:
            raise CaseValidationError("پرونده پیدا نشد.")
        if case.get("status") == "archived":
            raise CaseValidationError("یادداشت پرونده بایگانی‌شده قابل تغییر نیست.")
        if text:
            ok=db.save_case_lawyer_note(uid,cid,text)
        else:
            # Clearing an already-empty note is an idempotent success.
            db.clear_case_lawyer_note(uid,cid)
            ok=True
        if not ok: raise CaseValidationError("یادداشت ذخیره نشد یا پرونده قابل ویرایش نیست.")
        return self._send(200,{"ok":True,"data":{"note":db.get_case_lawyer_note(uid,cid)}})

    def _validate_calendar_due_at(self, due_at):
        if not isinstance(due_at, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:T(?:[01]\d|2[0-3]):[0-5]\d)?", due_at):
            raise ValueError("موعد باید به شکل YYYY-MM-DD یا همراه ساعت ثبت شود.")
        from datetime import date
        try: date.fromisoformat(due_at[:10])
        except ValueError as exc: raise ValueError("تاریخ موعد معتبر نیست.") from exc
        return due_at

    def _create_calendar_task(self, uid, data):
        if not isinstance(data, dict): raise ValueError("بدنه درخواست نامعتبر است.")
        title = str(data.get("title") or "").strip()
        if not title or len(title) > 500: raise ValueError("عنوان کار الزامی و حداکثر ۵۰۰ نویسه است.")
        due_at = self._validate_calendar_due_at(data.get("due_at"))
        case_id = data.get("case_id")
        reminder_days = data.get("reminder_days")
        if reminder_days not in (None, "", 0, 1, 3, 7, "0", "1", "3", "7"):
            raise ValueError("بازه یادآوری باید یکی از ۰، ۱، ۳ یا ۷ روز باشد.")
        reminder_days = int(reminder_days) if reminder_days not in (None, "") else None
        if reminder_days is not None and due_at is None:
            raise ValueError("برای تنظیم یادآوری باید موعد کار مشخص باشد.")
        if case_id not in (None, ""):
            try: case_id = int(case_id)
            except (TypeError, ValueError): raise ValueError("شناسه پرونده معتبر نیست.")
            task_id = db.add_case_task(uid, case_id, title, due_at=due_at, reminder_days=reminder_days)
            if not task_id: raise CaseValidationError("پرونده پیدا نشد یا کار ثبت نشد.")
            item_type = "task"
        else:
            task_id = db.add_task(uid, title, due_at=due_at, reminder_days=reminder_days)
            item_type = "user_task"
        return self._send(201, {"ok": True, "data": {"id": task_id, "item_type": item_type}})

    def _update_calendar_task(self, uid, task_id, data):
        if not isinstance(data, dict) or not isinstance(data.get("done"), bool):
            raise ValueError("وضعیت انجام کار باید true یا false باشد.")
        item_type = data.get("item_type")
        if item_type == "user_task":
            ok = db.set_task_done(uid, task_id, data["done"])
        elif item_type == "task":
            ok = db.set_case_task_done(uid, task_id, data["done"])
        else:
            raise ValueError("نوع کار برای تغییر وضعیت مشخص نشده است.")
        if not ok: raise CaseValidationError("کار پیدا نشد یا متعلق به این حساب نیست.")
        return self._send(200, {"ok": True, "data": {"task_id": task_id, "done": data["done"]}})

    def _calendar(self, uid):
        query = parse_qs(urlparse(self.path).query)
        start_date = (query.get("from", ["1900-01-01"])[0] or "1900-01-01")
        end_date = (query.get("to", ["2999-12-31"])[0] or "2999-12-31")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", start_date) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", end_date):
            raise ValueError("بازه تاریخ تقویم نامعتبر است.")
        from datetime import date
        try:
            start_obj, end_obj = date.fromisoformat(start_date), date.fromisoformat(end_date)
        except ValueError as exc:
            raise ValueError("تاریخ تقویم معتبر نیست.") from exc
        if end_obj < start_obj or (end_obj-start_obj).days > 370:
            raise ValueError("بازه تقویم حداکثر می‌تواند ۳۷۰ روز باشد.")
        items = db.list_user_calendar_items(uid, start_date, end_date, limit=1000)
        return self._send(200, {"ok": True, "data": {"items": items, "count": len(items), "from": start_date, "to": end_date}})

    def _recent_activity(self, uid):
        query = parse_qs(urlparse(self.path).query)
        try:
            limit = max(1, min(int(query.get("limit", [8])[0]), 20))
        except (TypeError, ValueError):
            limit = 8
        return self._send(200, {"ok": True, "data": {"items": db.list_recent_activity(uid, limit)}})

    def _record_recent_activity(self, uid, data):
        if not isinstance(data, dict) or set(data) != {"case_id", "activity_type"}:
            raise ValueError("اطلاعات فعالیت نامعتبر است.")
        if isinstance(data.get("case_id"), bool):
            raise ValueError("شناسه پرونده نامعتبر است.")
        try:
            case_id = int(data.get("case_id"))
        except (TypeError, ValueError):
            raise ValueError("شناسه پرونده نامعتبر است.")
        activity_type = str(data.get("activity_type") or "")
        if activity_type not in db.RECENT_ACTIVITY_LABELS:
            raise ValueError("نوع فعالیت پشتیبانی نمی‌شود.")
        if not db.record_recent_activity(uid, case_id, activity_type):
            return self._error(404, "case_not_found", "پرونده پیدا نشد یا متعلق به این حساب نیست.")
        return self._send(201, {"ok": True, "data": {"recorded": True}})

    def _unified_search(self, uid):
        query = parse_qs(urlparse(self.path).query)
        q = (query.get("q", [""])[0] or "").strip()
        raw_scopes = (query.get("scopes", [""])[0] or "").strip()
        scopes = [x.strip() for x in raw_scopes.split(",") if x.strip()] if raw_scopes else None
        try:
            limit = max(1, min(int(query.get("limit", [40])[0]), 60))
        except (TypeError, ValueError):
            limit = 40
        include_archived = (query.get("archived", ["0"])[0] or "0").lower() in {"1", "true", "yes"}
        data = search_user_workspace(uid, q, scopes=scopes, limit=limit, include_archived=include_archived)
        return self._send(200, {"ok": True, "data": data})

    def _legal_search(self, uid):
        query = parse_qs(urlparse(self.path).query)
        q = (query.get("q", [""])[0] or "").strip()
        if len(q) < 2 or len(q) > 200:
            raise ValueError("عبارت جست‌وجو باید بین ۲ تا ۲۰۰ نویسه باشد.")
        try:
            limit = max(1, min(int(query.get("limit", [8])[0]), 12))
        except (TypeError, ValueError):
            limit = 8
        laws = legal_law_search(q, limit)
        terms = glossary_lookup(q, min(limit, 8))
        items = []
        for rec in laws:
            citation = rec.get("citation") or {}
            items.append({
                "kind": rec.get("kind", "law"), "title": rec.get("title") or rec.get("law") or "منبع حقوقی",
                "law": rec.get("law", ""), "article": rec.get("article") or rec.get("ruling_number") or rec.get("consultation_number") or "",
                "snippet": (rec.get("clean_text") or rec.get("text") or rec.get("question") or "")[:2600],
                "citation_id": citation.get("id"), "source_file": citation.get("source_file") or rec.get("source_file"),
                "source_page": citation.get("page") or rec.get("source_page"),
                "source_status": rec.get("source_status") or rec.get("status") or "نامشخص",
                "date": rec.get("date") or rec.get("year") or ""
            })
        glossary = []
        for item in terms:
            glossary.append({"term": item.get("term") or item.get("title") or "", "definition": item.get("definition") or item.get("text") or item.get("description") or ""})
        return self._send(200, {"ok": True, "data": {"query": q, "items": items, "glossary": glossary, "count": len(items), "notice": "رتبه‌بندی جست‌وجو به معنی تأیید اعتبار یا قابلیت استناد منبع نیست؛ متن کامل و آخرین وضعیت باید بررسی شود."}})

    def _legal_source(self, uid):
        query = parse_qs(urlparse(self.path).query)
        cid = (query.get("id", [""])[0] or "").strip()
        if not cid or len(cid) > 160:
            raise ValueError("شناسه منبع نامعتبر است.")
        rec = legal_source_record(cid)
        if not rec:
            return self._error(404, "source_not_found", "منبع در بانک فعلی پیدا نشد.")
        citation = rec.get("citation") or {}
        return self._send(200, {"ok": True, "data": {"item": {
            "kind": rec.get("kind", "law"), "title": rec.get("title") or rec.get("law") or "منبع حقوقی",
            "law": rec.get("law", ""), "article": rec.get("article") or rec.get("ruling_number") or rec.get("consultation_number") or "",
            "text": rec.get("clean_text") or rec.get("text") or rec.get("question") or "",
            "citation": citation, "related": [{"title": x.get("title") or x.get("law") or "منبع مرتبط", "citation_id": (x.get("citation") or {}).get("id")} for x in legal_related_sources(rec, 6)],
            "notice": "منابع مرتبط صرفاً پیشنهاد پژوهشی بر اساس داده‌های موجود هستند؛ رابطه حقوقی یا اعتبار جاری را اثبات نمی‌کنند."
        }}})

    def _telegram_json_call(self, method, payload):
        if not BOT_TOKEN: raise RuntimeError("توکن ربات برای ارسال رسید تنظیم نشده است.")
        request = Request(f"https://api.telegram.org/bot{BOT_TOKEN}/{method}", data=json.dumps(payload,ensure_ascii=False).encode("utf-8"), headers={"Content-Type":"application/json"}, method="POST")
        with urlopen(request, timeout=25) as response:
            data=json.loads(response.read().decode("utf-8"))
        if not data.get("ok"): raise RuntimeError(str(data.get("description") or "Telegram API request failed"))
        return data.get("result")

    def _subscription_info(self, uid):
        pending = db.has_pending_payment_request(uid)
        return self._send(200,{"ok":True,"data":{"price_text":SUBSCRIPTION_PRICE_TEXT,"card_number":ADMIN_CARD_NUMBER,"card_holder":ADMIN_CARD_HOLDER,"pending_receipt":bool(pending),"notice":"پرداخت و فعال‌سازی اشتراک پس از بررسی دستی ادمین انجام می‌شود؛ ارسال رسید به معنی فعال‌شدن اشتراک نیست."}})

    def _submit_subscription_receipt(self, uid):
        if not BOT_TOKEN or not ADMIN_TELEGRAM_IDS:
            return self._error(503,"payment_review_unavailable","ارسال رسید فعلاً پیکربندی نشده است؛ لطفاً از مسیر پشتیبانی پیگیری کنید.")
        if db.has_pending_payment_request(uid):
            return self._error(409,"payment_receipt_pending","یک رسید شما هنوز در انتظار بررسی ادمین است.")
        content_type=self.headers.get("Content-Type","")
        if not content_type.lower().startswith("multipart/form-data"): raise ValueError("رسید باید با multipart/form-data ارسال شود.")
        try: length=int(self.headers.get("Content-Length","0"))
        except ValueError: length=0
        max_bytes=8*1024*1024
        if length<=0 or length>max_bytes+65536: raise ValueError("حجم رسید باید کمتر از ۸ مگابایت باشد.")
        body=self.rfile.read(length)
        if len(body)!=length: raise ValueError("آپلود رسید ناقص دریافت شد.")
        blob=(f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n").encode("utf-8")+body
        message=BytesParser(policy=policy.default).parsebytes(blob)
        image_part=next((p for p in message.walk() if p.get_content_disposition()=="form-data" and p.get_filename()),None)
        if image_part is None: raise ValueError("فایل رسید ارسال نشده است.")
        filename=Path(str(image_part.get_filename())).name
        suffix=Path(filename).suffix.lower()
        mime=image_part.get_content_type().lower()
        if suffix not in {".jpg",".jpeg",".png",".webp"} or mime not in {"image/jpeg","image/png","image/webp"}: raise ValueError("رسید باید تصویر JPG، PNG یا WEBP باشد.")
        raw=image_part.get_payload(decode=True) or b""
        if not raw or len(raw)>max_bytes: raise ValueError("تصویر رسید خالی یا بیش از حد مجاز است.")
        caption=""
        for part in message.walk():
            if part.get_content_disposition()=="form-data" and part.get_param("name",header="content-disposition")=="caption":
                caption=(part.get_content() or "").strip()[:500]
        first_admin=sorted(ADMIN_TELEGRAM_IDS)[0]
        boundary="----MachinaReceipt"+uuid.uuid4().hex
        chunks=[]
        def field(name,value):
            chunks.extend([f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode("utf-8")])
        field("chat_id",str(first_admin));field("caption","در حال ثبت رسید پرداخت اشتراک MACHINA…")
        chunks.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"{filename}\"\r\nContent-Type: {mime}\r\n\r\n".encode("utf-8")+raw+b"\r\n")
        chunks.append(f"--{boundary}--\r\n".encode("ascii"));payload=b"".join(chunks)
        request=Request(f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",data=payload,headers={"Content-Type":f"multipart/form-data; boundary={boundary}"},method="POST")
        try:
            with urlopen(request,timeout=35) as response: tg=json.loads(response.read().decode("utf-8"))
            if not tg.get("ok"): raise RuntimeError(str(tg.get("description") or "Telegram rejected the receipt image"))
            sent_message=tg.get("result") or {}; photos=sent_message.get("photo") or []
            file_id=(photos[-1].get("file_id") if photos else None)
            if not file_id: raise RuntimeError("Telegram did not return a photo file_id")
        except Exception:
            log.exception("Telegram receipt upload failed for user=%s",uid)
            return self._error(502,"receipt_upload_failed","ارسال تصویر رسید به تلگرام انجام نشد؛ دوباره تلاش کنید.")
        pid=db.create_payment_request(uid,file_id,caption)
        if not pid:
            try:self._telegram_json_call("deleteMessage",{"chat_id":first_admin,"message_id":sent_message.get("message_id")})
            except Exception:pass
            return self._error(409,"payment_receipt_pending","ثبت رسید انجام نشد؛ احتمالاً یک رسید دیگر در انتظار بررسی است.")
        row=db.get_payment_request(pid) or {"id":pid,"user_id":uid,"status":"pending","receipt_caption":caption}
        ref=row.get("payment_reference") or str(pid)
        admin_text=(f"💳 رسید پرداخت اشتراک #{pid}\n\n👤 Telegram ID: {uid}\n📦 پلن: اشتراک ماهانه\n🔖 کد پیگیری: {ref}\n📅 وضعیت: {row.get('status','pending')}"+(f"\n📝 توضیح کاربر: {caption}" if caption else ""))
        keyboard={"inline_keyboard":[[{"text":"✅ تأیید و فعال‌سازی","callback_data":f"payok:{pid}"},{"text":"❌ رد رسید","callback_data":f"payno:{pid}"}]]}
        notified=False
        try:
            self._telegram_json_call("editMessageCaption",{"chat_id":first_admin,"message_id":sent_message.get("message_id"),"caption":admin_text,"reply_markup":keyboard})
            notified=True
        except Exception:
            try:self._telegram_json_call("sendMessage",{"chat_id":first_admin,"text":admin_text,"reply_markup":keyboard});notified=True
            except Exception:log.exception("Could not attach payment controls for receipt %s",pid)
        for aid in sorted(ADMIN_TELEGRAM_IDS):
            if aid==first_admin: continue
            try:self._telegram_json_call("sendPhoto",{"chat_id":aid,"photo":file_id,"caption":admin_text,"reply_markup":keyboard});notified=True
            except Exception:
                try:self._telegram_json_call("sendMessage",{"chat_id":aid,"text":admin_text,"reply_markup":keyboard});notified=True
                except Exception:log.exception("Could not notify admin about payment receipt %s",pid)
        if not notified:
            log.error("Receipt %s stored but no admin notification confirmed",pid)
            return self._error(502,"receipt_admin_notify_failed","رسید ثبت شد اما اطلاع‌رسانی به ادمین تأیید نشد؛ کد پیگیری را نگه دارید و با پشتیبانی تماس بگیرید.")
        return self._send(201,{"ok":True,"data":{"submitted":True,"payment_id":pid,"payment_reference":ref,"status":"pending","notice":"رسید برای بررسی دستی ادمین ارسال شد؛ اشتراک هنوز فعال نشده است."}})

    def _read_service_multipart(self):
        content_type=self.headers.get("Content-Type","")
        if not content_type.lower().startswith("multipart/form-data"):
            raise ValueError("فرم پروفایل باید به‌صورت multipart ارسال شود.")
        try: length=int(self.headers.get("Content-Length","0"))
        except ValueError: length=0
        if length<=0 or length>6*1024*1024+65536: raise ValueError("حجم درخواست نامعتبر است؛ تصویر پروانه باید کمتر از ۶ مگابایت باشد.")
        body=self.rfile.read(length)
        if len(body)!=length: raise ValueError("آپلود ناقص دریافت شد.")
        msg=BytesParser(policy=policy.default).parsebytes((f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n").encode()+body)
        data={}; photo=None
        for part in msg.walk():
            if part.get_content_disposition()!="form-data": continue
            name=part.get_param("name",header="content-disposition")
            if not name: continue
            if part.get_filename():
                if name=="license_photo": photo=part
            else: data[name]=(part.get_content() or "").strip()
        if photo is None: raise ValueError("تصویر پروانه وکالت الزامی است؛ فقط برای بررسی ادمین ارسال می‌شود.")
        filename=Path(str(photo.get_filename())).name; suffix=Path(filename).suffix.lower(); mime=photo.get_content_type().lower(); raw=photo.get_payload(decode=True) or b""
        if suffix not in {".jpg",".jpeg",".png",".webp"} or mime not in {"image/jpeg","image/png","image/webp"} or not raw or len(raw)>6*1024*1024:
            raise ValueError("تصویر پروانه باید JPG، PNG یا WEBP و حداکثر ۶ مگابایت باشد.")
        return data,filename,mime,raw

    def _service_fields(self,data):
        keys=("full_name","phone","city","specialty","service_title","fee_type","fee_value","description")
        values={k:str(data.get(k) or "").strip() for k in keys}
        if values["fee_type"] not in {"fixed","percent"}: raise ValueError("نوع دستمزد نامعتبر است.")
        limits={"full_name":120,"phone":40,"city":100,"specialty":150,"service_title":200,"fee_value":100,"description":2000}
        if any(not values[k] for k in keys[:5]) or not values["fee_value"] or any(len(values[k])>v for k,v in limits.items()):
            raise ValueError("همه فیلدهای اصلی را تکمیل کنید و طول متن‌ها را در محدوده مجاز نگه دارید.")
        values["charitable"] = str(data.get("charitable","")).lower() in {"1","true","yes","on"}
        return values

    def _upload_service_license(self,uid,filename,mime,raw):
        if not BOT_TOKEN or not ADMIN_TELEGRAM_IDS: raise RuntimeError("ارسال پروانه برای بررسی ادمین پیکربندی نشده است.")
        aid=sorted(ADMIN_TELEGRAM_IDS)[0]; boundary="----MachinaLicense"+uuid.uuid4().hex
        chunks=[]
        for name,value in (("chat_id",str(aid)),("caption",f"تصویر پروانه وکالت ارسالی از حساب {uid}؛ در انتظار ثبت پروفایل")):
            chunks.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
        chunks.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"{filename}\"\r\nContent-Type: {mime}\r\n\r\n".encode()+raw+b"\r\n")
        chunks.append(f"--{boundary}--\r\n".encode())
        req=Request(f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",data=b"".join(chunks),headers={"Content-Type":f"multipart/form-data; boundary={boundary}"},method="POST")
        with urlopen(req,timeout=35) as response: result=json.loads(response.read().decode())
        if not result.get("ok"): raise RuntimeError(str(result.get("description") or "ارسال تصویر پروانه ناموفق بود."))
        sent=result.get("result") or {}; photos=sent.get("photo") or []
        if not photos: raise RuntimeError("تلگرام شناسه تصویر پروانه را برنگرداند.")
        return photos[-1]["file_id"],sent.get("message_id"),aid

    def _notify_service_admins(self,row,file_id,first_message_id=None,first_admin=None):
        keyboard={"inline_keyboard":[[{"text":"✅ تأیید خدمت","callback_data":f"serviceadmin:approve:{row['id']}"},{"text":"❌ رد خدمت","callback_data":f"serviceadmin:reject:{row['id']}"}]]}
        text=(f"📥 خدمت ارسالی از Mini App #{row['id']}\n👤 {row['full_name']}\n📞 {row['phone']}\n📍 {row['city']}\n⚖️ {row['specialty']}\n💼 {row['service_title']}\n💰 {row['fee_value']} {'تومان' if row['fee_type']=='fixed' else '٪'}\n📝 {row.get('description') or '—'}\n👤 Telegram ID: {row['user_id']}\nوضعیت: {row['status']}")
        sent=False
        for aid in sorted(ADMIN_TELEGRAM_IDS):
            try:
                if aid==first_admin and first_message_id:
                    self._telegram_json_call("editMessageCaption",{"chat_id":aid,"message_id":first_message_id,"caption":text[:1000],"reply_markup":keyboard})
                else:
                    self._telegram_json_call("sendPhoto",{"chat_id":aid,"photo":file_id,"caption":text[:1000],"reply_markup":keyboard})
                sent=True
            except Exception:
                try:self._telegram_json_call("sendMessage",{"chat_id":aid,"text":text,"reply_markup":keyboard}); sent=True
                except Exception:log.exception("Service listing admin notification failed: %s",aid)
        return sent

    def _create_service_listing(self,uid):
        data,filename,mime,raw=self._read_service_multipart(); values=self._service_fields(data)
        from .handlers import _validate_service_fields
        ok,msg=_validate_service_fields(values["full_name"],values["phone"],values["city"],values["specialty"],values["service_title"],values["fee_type"],values["fee_value"],values["description"])
        if not ok: raise ValueError(msg)
        file_id,msg_id,first_admin=self._upload_service_license(uid,filename,mime,raw)
        lid=db.create_service_listing(uid,values["full_name"],values["phone"],values["city"],values["specialty"],values["service_title"],values["fee_type"],values["fee_value"],values["description"],values["charitable"])
        row=db.get_service_listing(lid)
        if not row:
            try:self._telegram_json_call("deleteMessage",{"chat_id":first_admin,"message_id":msg_id})
            except Exception:pass
            return self._error(500,"service_save_failed","ثبت پروفایل انجام نشد.")
        notified = self._notify_service_admins(row,file_id,msg_id,first_admin)
        notice = ("پروفایل برای بررسی دستی ادمین ارسال شد؛ تا تأیید نهایی در فهرست عمومی نمایش داده نمی‌شود."
                  if notified else "پروفایل ذخیره شد و در انتظار بررسی است، اما ارسال اعلان ادمین ناموفق بود. لطفاً برای جلوگیری از ثبت تکراری، دوباره ارسال نکنید و با پشتیبانی تماس بگیرید.")
        return self._send(201 if notified else 202,{"ok":True,"data":{"item":row,"notification_sent":bool(notified),"notice":notice}})

    def _update_service_listing(self,uid,lid):
        old=db.get_service_listing(lid)
        if not old or int(old.get("user_id",-1))!=int(uid) or old.get("status")=="deleted": return self._error(404,"service_not_found","پروفایل خدمت پیدا نشد یا متعلق به این حساب نیست.")
        data,filename,mime,raw=self._read_service_multipart(); values=self._service_fields(data)
        from .handlers import _validate_service_fields
        ok,msg=_validate_service_fields(values["full_name"],values["phone"],values["city"],values["specialty"],values["service_title"],values["fee_type"],values["fee_value"],values["description"])
        if not ok: raise ValueError(msg)
        file_id,msg_id,first_admin=self._upload_service_license(uid,filename,mime,raw)
        if not db.update_service_listing(uid,lid,values["full_name"],values["phone"],values["city"],values["specialty"],values["service_title"],values["fee_type"],values["fee_value"],values["description"],values["charitable"]):
            try:self._telegram_json_call("deleteMessage",{"chat_id":first_admin,"message_id":msg_id})
            except Exception:pass
            return self._error(404,"service_not_found","پروفایل خدمت پیدا نشد یا متعلق به این حساب نیست.")
        row=db.get_service_listing(lid)
        notified = self._notify_service_admins(row,file_id,msg_id,first_admin)
        notice = ("ویرایش برای بررسی مجدد ادمین ارسال شد."
                  if notified else "ویرایش ذخیره شد و در انتظار بررسی است، اما اعلان ادمین ناموفق بود. لطفاً دوباره ارسال نکنید و با پشتیبانی تماس بگیرید.")
        return self._send(200 if notified else 202,{"ok":True,"data":{"item":row,"notification_sent":bool(notified),"notice":notice}})

    def _create_feedback(self, uid, data):
        if not isinstance(data, dict) or set(data) - {"kind", "message", "context"}:
            raise ValueError("گزارش پشتیبانی نامعتبر است.")
        kind = str(data.get("kind") or "support")
        message = str(data.get("message") or "").strip()
        context = str(data.get("context") or "").strip()
        if kind not in {"support", "user_report"} or not message or len(message) > 4000 or len(context) > 1000:
            raise ValueError("متن گزارش باید بین ۱ تا ۴۰۰۰ نویسه باشد.")
        db.add_feedback(uid, kind, message, context)
        return self._send(201, {"ok": True, "data": {"submitted": True}})

    def _clients(self, uid):
        query = parse_qs(urlparse(self.path).query)
        q = (query.get("q", [""])[0] or "").strip().casefold()
        try: limit = max(1, min(int(query.get("limit", [50])[0]), 100))
        except (TypeError, ValueError): limit = 50
        rows = db.list_clients(uid, limit=100)
        if q:
            rows = [x for x in rows if q in str(x.get("name", "")).casefold() or q in str(x.get("phone", "")).casefold()]
        return self._send(200, {"ok": True, "data": {"items": rows[:limit], "count": len(rows[:limit])}})

    def _client_detail(self, uid, client_id):
        item = db.get_client(uid, client_id)
        if not item: return self._error(404, "client_not_found", "موکل پیدا نشد.")
        return self._send(200, {"ok": True, "data": {"item": item, "cases": db.client_cases(uid, client_id)}})

    def _create_client(self, uid, data):
        if not isinstance(data, dict) or set(data) - {"name", "phone", "national_id", "note"}:
            raise ValueError("اطلاعات موکل نامعتبر است.")
        name = str(data.get("name") or "").strip()
        phone = str(data.get("phone") or "").strip()
        national_id = str(data.get("national_id") or "").strip()
        note = str(data.get("note") or "").strip()
        if not name or len(name) > 120 or len(phone) > 40 or len(national_id) > 20 or len(note) > 2000:
            raise ValueError("نام یا یکی از اطلاعات موکل نامعتبر یا بیش از حد مجاز است.")
        cid = db.create_client(uid, name, phone, national_id, note)
        if not cid: raise ValueError("ثبت موکل انجام نشد.")
        return self._send(201, {"ok": True, "data": {"item": db.get_client(uid, cid)}})

    def _update_client(self, uid, client_id, data):
        if not isinstance(data, dict) or set(data) - {"name", "phone", "national_id", "note"}:
            raise ValueError("اطلاعات ویرایش موکل نامعتبر است.")
        old = db.get_client(uid, client_id)
        if not old: return self._error(404, "client_not_found", "موکل پیدا نشد.")
        values = {k: str(data.get(k, old.get(k) or "")).strip() for k in ("name", "phone", "national_id", "note")}
        if not values["name"] or len(values["name"]) > 120 or len(values["phone"]) > 40 or len(values["national_id"]) > 20 or len(values["note"]) > 2000:
            raise ValueError("اطلاعات موکل نامعتبر یا بیش از حد مجاز است.")
        if not db.update_client(uid, client_id, **values):
            return self._error(404, "client_not_found", "موکل پیدا نشد.")
        return self._send(200, {"ok": True, "data": {"item": db.get_client(uid, client_id)}})

    def _delete_client(self, uid, client_id):
        if not db.delete_client(uid, client_id): return self._error(404, "client_not_found", "موکل پیدا نشد.")
        return self._send(200, {"ok": True, "data": {"deleted": True}})

    def _link_client_case(self, uid, client_id, case_id):
        if not db.link_client_case(uid, client_id, case_id):
            return self._error(404, "link_failed", "موکل یا پرونده پیدا نشد یا متعلق به این حساب نیست.")
        return self._send(201, {"ok": True, "data": {"linked": True}})

    def _calculator_catalog(self, uid):
        years = [{"year": y, "provisional": y in MAHR_PROVISIONAL_YEARS} for y in sorted(MAHR_ANNUAL_INDEX)]
        return self._send(200, {"ok": True, "data": {"items": [
            {"id": "mahr", "title": "مهریه به نرخ روز", "unit": "تومان"},
            {"id": "diya", "title": "دیه ثابت سال ۱۴۰۵", "unit": "تومان"},
            {"id": "delay", "title": "خسارت تأخیر تأدیه با شاخص ورودی", "unit": "تومان"},
            {"id": "court_fee", "title": "هزینه دادرسی تقریبی", "unit": "ریال"},
            {"id": "lawyer_fee", "title": "حق‌الوکاله تعرفه‌ای دعوای مالی", "unit": "ریال"},
            {"id": "deadline", "title": "جمع روزهای تقویمی", "unit": "روز"},
            {"id": "quick_percent", "title": "درصد از مبلغ", "unit": "تومان"},
            {"id": "rial_convert", "title": "تبدیل تومان و ریال", "unit": "تومان/ریال"},
            {"id": "installment", "title": "قسط‌بندی مبلغ", "unit": "تومان"},
            {"id": "date_diff", "title": "فاصله دو تاریخ شمسی یا میلادی", "unit": "روز"},
            {"id": "date_convert", "title": "تبدیل تاریخ شمسی و میلادی", "unit": "تاریخ"},
            {"id": "iran_today", "title": "تاریخ امروز ایران", "unit": "تاریخ"},
            {"id": "alcohol_fine", "title": "برآورد جزای نقدی ماده ۷۰۲", "unit": "تومان"}
        ], "mahr_years": years, "diyah": {"normal": DIYA_FULL_1405_NORMAL, "haram": DIYA_FULL_1405_HARAM}, "diyah_presets": {"head": HEAD_WOUND_PCTS, "color": COLOR_PCTS}, "source_notes": CALC_SOURCE_NOTES}})

    def _run_calculator(self, uid, data):
        if not isinstance(data, dict): raise ValueError("ورودی محاسبه نامعتبر است.")
        kind = str(data.get("kind") or "")
        def amount(key):
            value = calculator_parse_amount(data.get(key))
            if value is None or value <= 0: raise ValueError("مبلغ واردشده معتبر نیست.")
            return value
        result = {"kind": kind}
        if kind == "mahr":
            value = amount("amount"); year = int(data.get("contract_year", 0)); target = max(MAHR_ANNUAL_INDEX)
            if year not in MAHR_ANNUAL_INDEX: raise ValueError("برای سال عقد واردشده شاخصی در جدول فعلی وجود ندارد.")
            result.update({"amount": calculator_mahr_value(value, MAHR_ANNUAL_INDEX[year], MAHR_ANNUAL_INDEX[target]), "principal": value, "contract_year": year, "reference_year": target, "contract_index": MAHR_ANNUAL_INDEX[year], "reference_index": MAHR_ANNUAL_INDEX[target], "provisional": year in MAHR_PROVISIONAL_YEARS or target in MAHR_PROVISIONAL_YEARS, "formula": "مبلغ × (شاخص سال مرجع ÷ شاخص سال عقد)"})
        elif kind == "diya":
            mode = str(data.get("mode") or "custom")
            label = "درصد دلخواه"; month_type = "normal"
            if mode == "full_normal": pct=100.0; base=DIYA_FULL_1405_NORMAL; label="دیه کامل ماه غیرحرام"
            elif mode == "full_haram": pct=100.0; base=DIYA_FULL_1405_HARAM; month_type="haram"; label="دیه کامل ماه حرام (مشروط به احراز شرایط قانونی)"
            elif mode in {"head","color"}:
                preset = str(data.get("preset") or "")
                choices = HEAD_WOUND_PCTS if mode=="head" else COLOR_PCTS
                if preset not in choices: raise ValueError("نوع جراحت یا تغییر رنگ معتبر نیست.")
                pct=float(choices[preset]); base=DIYA_FULL_1405_NORMAL; label=preset
            else:
                pct = float(data.get("percent", 0)); base=DIYA_FULL_1405_NORMAL
                if pct < 0 or pct > 100: raise ValueError("درصد باید بین صفر تا ۱۰۰ باشد.")
            result.update({"amount": calculator_diyah_percentage(base, pct), "label":label,"percent": pct, "base": base, "year": 1405, "month_type": month_type, "warning": "این محاسبه فقط اعمال درصد ثابت بر دیه کامل است؛ ارش، تعدد صدمات و شرایط تغلیظ نیازمند بررسی مستقل‌اند. درصد جراحات و تغییر رنگ با مبنای غیرحرام محاسبه می‌شود."})
        elif kind == "delay":
            result.update(calculator_delay_damage(amount("principal"), float(data.get("index_start", 0)), float(data.get("index_end", 0))))
        elif kind == "court_fee":
            value = amount("amount_rial"); stage = str(data.get("stage") or "first")
            result.update({"amount": calculator_court_fee(value, stage), "principal": value, "unit": "ریال", "stage": stage, "warning": "تعرفه جاری و مبلغ نهایی سامانه مرجع ملاک پرداخت است."})
        elif kind == "lawyer_fee":
            value = amount("amount_rial"); total = calculator_lawyer_fee(value); first, appeal = calculator_lawyer_fee_split(total)
            result.update({"amount": total, "first_instance": first, "appeal": appeal, "principal": value, "unit": "ریال", "warning": "فقط برآورد تعرفه‌ای دعوای مالی بر اساس جدول موجود؛ توافق طرفین و پرونده‌های خاص ممکن است متفاوت باشد."})
        elif kind == "deadline":
            raw_start = str(data.get("start_date") or "")
            parsed_start = parse_jalali(raw_start) or parse_gregorian(raw_start)
            days = int(data.get("days", 0))
            if not parsed_start or days < 0 or days > 3650: raise ValueError("تاریخ یا تعداد روز نامعتبر است.")
            start = parsed_start[3]; end = calculator_add_days(start, days)
            sy,sm,sd = gregorian_to_jalali(start); ey,em,ed = gregorian_to_jalali(end)
            result.update({"start_date_gregorian": start.isoformat(), "start_date_jalali":f"{sy:04d}/{sm:02d}/{sd:02d}", "days": days, "end_date_gregorian": end.isoformat(), "end_date_jalali":f"{ey:04d}/{em:02d}/{ed:02d}", "warning": "فقط جمع روز تقویمی است؛ تعطیلات، قواعد ابلاغ و مقررات خاص مهلت را اعمال نمی‌کند."})
        elif kind == "quick_percent":
            base = amount("amount"); pct = float(data.get("percent", -1))
            if pct < 0 or pct > 10000: raise ValueError("درصد باید بین صفر تا ۱۰۰۰۰ باشد.")
            result.update({"principal":base,"percent":pct,"amount":round(base*pct/100),"unit":"تومان"})
        elif kind == "rial_convert":
            base = calculator_parse_amount(data.get("amount"))
            if base is None or base < 0: raise ValueError("مبلغ معتبر نیست.")
            direction = str(data.get("direction") or "toman_to_rial")
            if direction == "toman_to_rial": result.update({"input":base,"output":base*10,"direction":direction,"unit":"ریال"})
            elif direction == "rial_to_toman": result.update({"input":base,"output":base/10,"direction":direction,"unit":"تومان"})
            else: raise ValueError("جهت تبدیل نامعتبر است.")
        elif kind == "installment":
            total = amount("total"); count = int(data.get("count", 0))
            if count < 1 or count > 600: raise ValueError("تعداد اقساط باید بین ۱ تا ۶۰۰ باشد.")
            each = total // count
            result.update({"total":total,"count":count,"installment":each,"remainder":total-each*count,"unit":"تومان","warning":"این فقط تقسیم ریاضی مبلغ است و درباره شرایط قانونی یا توان پرداخت اظهارنظر نمی‌کند."})
        elif kind == "date_diff":
            a = str(data.get("date_a") or ""); b = str(data.get("date_b") or "")
            pa = parse_jalali(a) or parse_gregorian(a); pb = parse_jalali(b) or parse_gregorian(b)
            if not pa or not pb: raise ValueError("هر دو تاریخ را با قالب شمسی ۱۴۰۵/۰۱/۰۱ یا میلادی 2026/01/01 وارد کنید.")
            delta=(pb[3]-pa[3]).days
            result.update({"date_a_gregorian":pa[3].isoformat(),"date_b_gregorian":pb[3].isoformat(),"days":abs(delta),"direction":"بعد از تاریخ اول" if delta>0 else "قبل از تاریخ اول" if delta<0 else "دو تاریخ یکسان‌اند","warning":"فاصله تقویمی دو تاریخ است؛ قواعد خاص احتساب مواعد قضایی را اعمال نمی‌کند."})
        elif kind == "date_convert":
            value = str(data.get("value") or ""); parsed = parse_jalali(value) or parse_gregorian(value)
            if not parsed: raise ValueError("تاریخ معتبر نیست؛ نمونه: ۱۴۰۵/۰۶/۲۹ یا 2026/09/20")
            g=parsed[3]; jy,jm,jd=gregorian_to_jalali(g)
            result.update({"jalali":f"{jy:04d}/{jm:02d}/{jd:02d}","gregorian":g.strftime("%Y/%m/%d")})
        elif kind == "iran_today":
            from datetime import datetime
            from zoneinfo import ZoneInfo
            now=datetime.now(ZoneInfo("Asia/Tehran")); g=now.date(); jy,jm,jd=gregorian_to_jalali(g)
            result.update({"jalali":f"{jy:04d}/{jm:02d}/{jd:02d}","gregorian":g.strftime("%Y/%m/%d"),"time":now.strftime("%H:%M"),"timezone":"Asia/Tehran"})
        elif kind == "alcohol_fine":
            value=amount("value_toman")
            result.update({"amount":alcohol_article_702_fine(value),"principal":value,"unit":"تومان","formula":"۵ برابر ارزش عرفی مشروبات مکشوفه","warning":"این صرفاً محاسبه ضریب قانونی ذکرشده در ماژول فعلی است؛ انطباق عنوان اتهام و متن جاری قانون باید مستقل بررسی شود."})
        else: raise ValueError("نوع محاسبه پشتیبانی نمی‌شود.")
        return self._send(200, {"ok": True, "data": {"result": result}})

    def _create_referral_request(self, uid, data):
        if not isinstance(data,dict) or set(data)-{"topic","city","urgency","details","consent"}: raise ValueError("اطلاعات درخواست معرفی نامعتبر است.")
        topic=str(data.get("topic") or "").strip(); city=str(data.get("city") or "").strip(); urgency=str(data.get("urgency") or "normal"); details=str(data.get("details") or "").strip()
        if not topic or len(topic)>160 or not city or len(city)>100 or len(details)<10 or len(details)>4000: raise ValueError("موضوع، شهر و شرح درخواست را با طول مجاز وارد کنید.")
        if urgency not in {"normal","soon","urgent"}: raise ValueError("سطح فوریت نامعتبر است.")
        if data.get("consent") is not True: raise ValueError("برای ارسال درخواست معرفی باید با اشتراک‌گذاری شرح بدون اطلاعات تماس با پشتیبانی موافقت کنید.")
        if not BOT_TOKEN or not ADMIN_TELEGRAM_IDS: return self._error(503,"referral_admin_unavailable","ثبت درخواست معرفی فعلاً پیکربندی نشده است؛ لطفاً از پشتیبانی استفاده کنید.")
        rid=db.create_referral_request(uid,topic,city,urgency,details,True)
        services=db.list_matching_services(topic,city,8)
        rows=[[{"text":f"📨 ارسال به {str(x.get('service_title') or 'خدمت')[:30]} | {str(x.get('city') or '')[:15]}","callback_data":f"refadmin:send:{rid}:{x['id']}"}] for x in services]
        rows.append([{"text":"❌ فعلاً بدون معرفی","callback_data":f"refadmin:close:{rid}"}])
        admin_text=(f"🤝 درخواست معرفی #{rid}\n\nموضوع: {topic}\nشهر: {city}\nفوریت: {urgency}\n\nشرح متقاضی:\n{details[:3500]}\n\n⚠️ اطلاعات تماس متقاضی تا مرحله پذیرش اولیه برای وکیل ارسال نمی‌شود.")
        notified=False
        for aid in sorted(ADMIN_TELEGRAM_IDS):
            try:self._telegram_json_call("sendMessage",{"chat_id":aid,"text":admin_text,"reply_markup":{"inline_keyboard":rows}});notified=True
            except Exception:log.exception("Referral request admin notification failed: id=%s admin=%s",rid,aid)
        return self._send(201,{"ok":True,"data":{"id":rid,"status":"new","admin_notified":notified,"notice":"درخواست ثبت شد؛ اطلاعات تماس یا مدارک محرمانه در شرح عمومی وارد نشده‌اند." if notified else "درخواست ثبت شد اما اطلاع‌رسانی به ادمین تأیید نشد؛ از پشتیبانی پیگیری کنید."}})

    def _referrals(self, uid):
        own = db.list_referrals_for_user(uid, 30)
        incoming = db.list_referral_matches_for_lawyer(uid, 30)
        safe_own = [{k:r.get(k) for k in ("id","topic","city","urgency","status","created_at","updated_at")} for r in own]
        safe_incoming = [{k:r.get(k) for k in ("id","referral_id","topic","city","urgency","details","status","referral_status","service_title","specialty","full_name","phone","created_at","updated_at")} for r in incoming]
        return self._send(200,{"ok":True,"data":{"own_requests":safe_own,"incoming_matches":safe_incoming,"notice":"اطلاعات تماس متقاضی تا پذیرش اولیه نمایش داده نمی‌شود؛ پس از پذیرش، ارتباط از طریق ربات تلگرام اطلاع‌رسانی می‌شود."}})

    def _update_referral_match(self, uid, match_id, data):
        if not isinstance(data,dict): raise ValueError("درخواست تغییر وضعیت معرفی نامعتبر است.")
        status=str(data.get("status") or "")
        if status not in {"accepted","declined","more_info"}: raise ValueError("وضعیت انتخاب‌شده معتبر نیست.")
        match=db.get_referral_match(match_id)
        if not match or int(match.get("lawyer_user_id") or 0)!=int(uid): return self._error(404,"referral_not_found","معرفی پیدا نشد یا متعلق به این حساب نیست.")
        if match.get("status") not in {"sent","more_info"}: return self._error(409,"referral_already_processed","این معرفی قبلاً بررسی شده است.")
        note=str(data.get("note") or "").strip()[:1000]
        if not db.update_referral_match(match_id,uid,status,note): return self._error(409,"referral_update_failed","تغییر وضعیت معرفی انجام نشد.")
        notifications=[]
        client_id=int(match.get("client_user_id") or 0)
        if status=="accepted":
            client_text=(f"✅ یک وکیل برای درخواست #{match['referral_id']} پذیرش اولیه انجام داد.\n\nوکیل: {match.get('full_name') or '—'}\nخدمت: {match.get('service_title') or '—'}\n📞 تماس وکیل: {match.get('phone') or 'از طریق پروفایل ثبت‌شده'}\n\nاطلاعات تماس شما پس از این مرحله در اختیار وکیل قرار می‌گیرد تا ارتباط پرونده را پیگیری کند. اگر تمایل به ادامه ندارید، از پشتیبانی درخواست لغو ارتباط کنید.")
            try:self._telegram_json_call("sendMessage",{"chat_id":client_id,"text":client_text});notifications.append("client_notified")
            except Exception:log.exception("Referral acceptance client notification failed: match=%s",match_id)
            try:self._telegram_json_call("sendMessage",{"chat_id":uid,"text":f"📞 پذیرش اولیه معرفی #{match['referral_id']} ثبت شد. شناسه تلگرام متقاضی: {client_id}\nبرای حفظ حریم خصوصی، اطلاعات تماس فقط در همین مرحله از فرایند معرفی ارائه می‌شود."});notifications.append("lawyer_notified")
            except Exception:log.exception("Referral acceptance lawyer notification failed: match=%s",match_id)
        elif status=="declined":
            try:self._telegram_json_call("sendMessage",{"chat_id":client_id,"text":f"❌ وکیل انتخاب‌شده درخواست #{match['referral_id']} را نپذیرفت. درخواست برای بررسی گزینه دیگری در اختیار پشتیبانی است."});notifications.append("client_notified")
            except Exception:log.exception("Referral decline client notification failed: match=%s",match_id)
        else:
            try:self._telegram_json_call("sendMessage",{"chat_id":client_id,"text":f"❓ وکیل برای معرفی #{match['referral_id']} اطلاعات بیشتری لازم دارد. لطفاً موارد تکمیلی را از طریق ربات ارسال کنید.","reply_markup":{"inline_keyboard":[[{"text":"📝 ارسال اطلاعات تکمیلی","callback_data":f"refinfo:{match['referral_id']}"}]]}});notifications.append("client_notified")
            except Exception:log.exception("Referral more-info client notification failed: match=%s",match_id)
        return self._send(200,{"ok":True,"data":{"updated":True,"status":status,"notifications":notifications,"notice":"وضعیت ثبت شد؛ اگر پیام تلگرام ارسال نشده باشد، وضعیت همچنان ذخیره شده و باید از پشتیبانی پیگیری شود."}})

    def _important_dates(self, uid):
        rows = db.list_case_important_dates(uid, 200)
        db.init_case_reminders_table()
        with db.conn() as c:
            active = {int(r[0]) for r in c.execute("SELECT case_date_id FROM case_date_reminders WHERE user_id=? AND enabled=1", (int(uid),)).fetchall()}
        for row in rows: row["reminder_enabled"] = int(row.get("id") or 0) in active
        return self._send(200, {"ok": True, "data": {"items": rows, "count": len(rows), "notice":"تاریخ‌های استخراج‌شده باید با سند اصلی بررسی شوند؛ یادآوری یک روز قبل به معنی تشخیص مهلت قانونی نیست."}})

    def _set_important_date_reminder(self, uid, date_id, data):
        if not isinstance(data, dict) or not isinstance(data.get("enabled"), bool): raise ValueError("وضعیت یادآوری باید true یا false باشد.")
        if not db.set_case_date_reminder(uid, date_id, data["enabled"]): return self._error(404, "important_date_not_found", "تاریخ پیدا نشد یا متعلق به این حساب نیست.")
        return self._send(200, {"ok": True, "data": {"date_id":date_id,"enabled":data["enabled"],"reminder":"یک روز قبل از تاریخ ثبت‌شده"}})

    def _tax_screen_upload(self, uid):
        content_type = self.headers.get("Content-Type", "")
        if not content_type.lower().startswith("multipart/form-data"): raise ValueError("تصویر باید با multipart/form-data ارسال شود.")
        try: length = int(self.headers.get("Content-Length", "0"))
        except ValueError: length = 0
        max_bytes = min(MAX_FILE_MB, 8) * 1024 * 1024
        if length <= 0 or length > max_bytes + 65536: raise ValueError("حجم تصویر نامعتبر یا بیش از حد مجاز است.")
        body = self.rfile.read(length)
        if len(body) != length: raise ValueError("آپلود تصویر ناقص دریافت شد.")
        blob = (f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n").encode("utf-8") + body
        message = BytesParser(policy=policy.default).parsebytes(blob)
        image_part = next((p for p in message.walk() if p.get_content_disposition()=="form-data" and p.get_filename()), None)
        if image_part is None: raise ValueError("فایل تصویری ارسال نشده است.")
        name = Path(str(image_part.get_filename())).name
        suffix = Path(name).suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png", ".webp"}: raise ValueError("فقط JPG، PNG و WEBP پشتیبانی می‌شوند.")
        raw = image_part.get_payload(decode=True) or b""
        if not raw or len(raw) > max_bytes: raise ValueError("حجم تصویر خالی یا بیش از حد مجاز است.")
        fd, tmp = tempfile.mkstemp(prefix="machina-tax-screen-", suffix=suffix)
        try:
            with os.fdopen(fd,"wb") as out: out.write(raw)
            ocr_text, diag = extract_with_diagnostics(Path(tmp))
            answers = {"activity":str(parse_qs(urlparse(self.path).query).get("activity",[""])[0])[:20]}
            guide = build_tax_screen_guide(ocr_text, answers)
            return self._send(200, {"ok":True,"data":{"text":guide,"ocr_chars":len(ocr_text or ""),"diagnostics":diag if isinstance(diag,dict) else {},"notice":"OCR محلی است؛ گزینه‌های مالیاتی از روی تصویر به‌صورت قطعی انتخاب نمی‌شوند."}})
        finally:
            try: Path(tmp).unlink(missing_ok=True)
            except OSError: pass

    def _contract_review(self, uid, cid, data):
        if not isinstance(data, dict): raise ValueError("درخواست بررسی قرارداد نامعتبر است.")
        case = CaseService().get(uid, cid)
        if not case or str(case.get("status") or "").lower()=="archived": return self._error(404,"case_not_found","پرونده فعال پیدا نشد.")
        playbook_id = str(data.get("playbook_id") or "")
        checklist = build_playbook_checklist(playbook_id)
        if not checklist: raise ValueError("الگوی بررسی قرارداد معتبر نیست.")
        if not (AI_ENABLED and DEEPSEEK_API_KEY and AI_EXTERNAL_DATA_CONSENT):
            return self._error(409,"ai_consent_required","تنظیمات AI، کلید سرویس یا رضایت ارسال داده به سرویس خارجی فعال نیست؛ هیچ متنی ارسال نشد.")
        text = db.get_case_text(uid,cid)
        if not text.strip(): return self._error(400,"case_text_missing","متن استخراج‌شده‌ای برای بررسی وجود ندارد. ابتدا OCR یا استخراج متن را تکمیل کنید.")
        entitlement = AIEntitlementService()
        ok, reservation = entitlement.reserve_question(uid)
        if not ok or not reservation: return self._error(402,"ai_quota_unavailable","سهمیه AI در دسترس نیست؛ هیچ درخواستی ارسال نشد.")
        try:
            report = review_contract_risks(text, checklist["title"], checklist, preference_uid=uid)
            entitlement.commit(uid,reservation)
            return self._send(200,{"ok":True,"data":{"report":report,"playbook":checklist["title"],"notice":"گزارش اولیه AI است؛ نقل‌قول‌ها و پیشنهادها باید با متن کامل قرارداد وکیلانه کنترل شوند."}})
        except Exception:
            entitlement.refund(uid,reservation)
            log.exception("Mini App contract playbook review failed for user=%s case=%s",uid,cid)
            return self._error(502,"contract_review_failed","بررسی قرارداد انجام نشد؛ سهمیه بازگردانده شد و پرونده تغییر نکرد.")

    def _guide_catalog(self, uid):
        items = [
            {"id":"check","title":"راهنمای چک و سفته","description":"مسیر دارنده یا صادرکننده و چک‌لیست مدارک"},
            {"id":"ejare","title":"راهنمای اجاره و تخلیه","description":"مسیر موجر یا مستأجر"},
            {"id":"family","title":"راهنمای مهریه و اعسار","description":"مسیر طلبکار یا بدهکار مهریه"},
            {"id":"shora","title":"شورا و دادگاه صلح","description":"بررسی موضوع، مبلغ و وضعیت مدارک"},
            {"id":"tax","title":"راهنمای مالیاتی","description":"راهنمای محلی بر اساس نوع فعالیت و هدف"},
        ]
        return self._send(200, {"ok": True, "data": {"items": items, "notice":"راهنماها عمومی‌اند و مقررات، نصاب‌ها و مهلت‌ها باید با منبع رسمی روز کنترل شوند."}})

    def _run_guide(self, uid, kind, data):
        if not isinstance(data, dict): raise ValueError("ورودی راهنما نامعتبر است.")
        if kind == "check":
            role = str(data.get("role") or ""); topic = str(data.get("topic") or "")
            topics = HOLDER_TOPICS if role == "holder" else DRAWER_TOPICS if role == "drawer" else {}
            if topic not in topics: raise ValueError("نقش یا موضوع چک معتبر نیست.")
            result = build_check_guide(role, topic)
        elif kind == "family":
            role = str(data.get("role") or ""); topic = str(data.get("topic") or "")
            topics = CREDITOR_TOPICS if role == "creditor" else DEBTOR_TOPICS if role == "debtor" else {}
            if topic not in topics: raise ValueError("نقش یا موضوع مهریه معتبر نیست.")
            result = build_family_guide(role, topic)
        elif kind == "ejare":
            role = str(data.get("role") or ""); topic = str(data.get("topic") or "")
            topics = TENANT_TOPICS if role == "tenant" else LANDLORD_TOPICS if role == "landlord" else {}
            if topic not in topics: raise ValueError("نقش یا موضوع اجاره معتبر نیست.")
            result = build_ejare_guide(role, topic)
        elif kind == "shora":
            answers = {k: str(data.get(k) or default) for k, default in (("topic","other"),("amount","unknown"),("docs","no"))}
            if answers["topic"] not in SHORA_TOPICS or answers["amount"] not in SHORA_AMOUNT_BANDS or answers["docs"] not in SHORA_HAS_DOC: raise ValueError("پاسخ‌های راهنمای شورا معتبر نیستند.")
            result = build_shora_guide(answers)
        elif kind == "tax":
            answers = {k: str(data.get(k) or default) for k, default in (("activity","other"),("task","unknown"),("docs","unknown"),("income","unknown"))}
            if answers["activity"] not in TAX_ACTIVITIES or answers["task"] not in TAX_TASKS or answers["income"] not in TAX_INCOME_BANDS or answers["docs"] not in {"yes","no","unknown"}: raise ValueError("پاسخ‌های راهنمای مالیاتی معتبر نیستند.")
            result = build_tax_guide(answers)
        else: raise ValueError("نوع راهنما پشتیبانی نمی‌شود.")
        return self._send(200, {"ok": True, "data": {"text": result, "kind": kind, "notice":"این خروجی راهنمای عمومی است؛ جایگزین بررسی سند، مقررات جاری یا مشاوره پرونده‌محور نیست."}})

    def _guided_tree_start(self, uid, kind, data):
        if not isinstance(data, dict): raise ValueError("ورودی درخت بررسی نامعتبر است.")
        cid = data.get("case_id")
        text = str(data.get("text") or "")
        if cid is not None:
            try: cid = int(cid)
            except (TypeError, ValueError): raise ValueError("شناسه پرونده نامعتبر است.")
            case = CaseService().get(uid, cid)
            if not case: return self._error(404, "case_not_found", "پرونده پیدا نشد.")
            docs = db.get_case_documents(uid, cid)
            if not text and docs:
                text = "\n\n".join(str(x.get("extracted_text") or "") for x in docs if x.get("extracted_text"))[:120000]
        if not text or len(text) > 120000: raise ValueError("متن قابل بررسی باید بین ۱ تا ۱۲۰۰۰۰ نویسه باشد.")
        starters = {"contract":interactive_contract_start,"claims":interactive_claims_start,"property":interactive_property_start,"check":interactive_check_start,"lease":interactive_lease_start}
        state = starters[kind](text)
        node = None
        session_id = None
        if state.get("status") == "active":
            from . import contract_tree, claims_tree, property_tree, check_tree, ejare_tree
            node_map = {"contract":contract_tree._INTERACTIVE_NODES,"claims":claims_tree._INTERACTIVE_NODES,"property":property_tree._INTERACTIVE_NODES,"check":check_tree._INTERACTIVE_NODES,"lease":ejare_tree._INTERACTIVE_NODES}
            nodes = node_map[kind]
            node = nodes[state.get("index", 0)] if state.get("index", 0) < len(nodes) else None
            session_id = uuid.uuid4().hex
            with _GUIDED_TREE_LOCK:
                now = time.monotonic()
                expired = [k for k,v in _GUIDED_TREE_SESSIONS.items() if v.get("expires", 0) <= now]
                for key in expired: _GUIDED_TREE_SESSIONS.pop(key, None)
                _GUIDED_TREE_SESSIONS[(int(uid), session_id)] = {"kind":kind,"state":state,"expires":now+3600}
        public_state = {"status":state.get("status"),"index":state.get("index",0)}
        return self._send(200, {"ok": True, "data": {"state": public_state, "session_id":session_id, "node": node, "summary":state if state.get("status") != "active" else None,"notice":"این درخت تصمیم داخلی و بدون AI است؛ وضعیت و متن اسناد در سمت سرور و مختص حساب شما نگهداری می‌شود."}})

    def _guided_tree_step(self, uid, kind, data):
        if not isinstance(data, dict): raise ValueError("ورودی مرحله درخت بررسی نامعتبر است.")
        session_id = str(data.get("session_id") or "")
        choice = str(data.get("choice") or "")
        if not re.fullmatch(r"[0-9a-f]{32}", session_id): raise ValueError("شناسه نشست درخت نامعتبر است.")
        key = (int(uid), session_id)
        with _GUIDED_TREE_LOCK:
            entry = _GUIDED_TREE_SESSIONS.get(key)
            if not entry or entry.get("expires", 0) <= time.monotonic() or entry.get("kind") != kind:
                _GUIDED_TREE_SESSIONS.pop(key, None)
                return self._error(404, "guided_tree_expired", "نشست بررسی منقضی شده است؛ درخت را دوباره شروع کنید.")
            state = entry["state"]
            steppers = {"contract":interactive_contract_step,"claims":interactive_claims_step,"property":interactive_property_step,"check":interactive_check_step,"lease":interactive_lease_step}
            result = steppers[kind](state, choice)
            if result.get("status") == "question":
                entry["state"] = result.get("state") or state
                entry["expires"] = time.monotonic()+3600
                public_state = {"status":"active","index":entry["state"].get("index",0)}
                payload = {"status":"question","state":public_state,"node":result.get("node"),"summary":None}
            else:
                _GUIDED_TREE_SESSIONS.pop(key, None)
                payload = {"status":result.get("status","complete"),"state":{"status":result.get("status","complete")},"node":None,"summary":result}
        return self._send(200, {"ok": True, "data": {"result": payload, "notice":"پاسخ‌ها توسط وکیل انتخاب شده‌اند؛ نتیجه جایگزین بررسی اصل اسناد و مقررات نیست."}})


    def _me(self, uid):
        user = get_user(uid)
        if not user:
            return self._error(404, "user_not_found", "کاربر در سیستم پیدا نشد.")
        safe = dict(user)
        for key in ("phone", "phone_hash", "lawyer_code", "password_hash"):
            safe.pop(key, None)
        return self._send(200, {"ok": True, "data": {"user": safe, "api_version": API_VERSION}})

    def _cases(self, uid):
        query = parse_qs(urlparse(self.path).query)
        try:
            limit = max(1, min(int(query.get("limit", [50])[0]), 100))
        except ValueError:
            limit = 50
        q = (query.get("q", [""])[0] or "").strip()
        include_archived = query.get("archived", ["0"])[0].lower() in {"1", "true", "yes"}
        cases = CaseService().list(uid, limit, query=q, include_archived=include_archived)
        pinned_ids = set(db.list_pinned_case_ids(uid))
        for item in cases:
            item["pinned"] = int(item.get("id") or 0) in pinned_ids
        cases.sort(key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)
        cases.sort(key=lambda item: not item.get("pinned", False))
        return self._send(200, {"ok": True, "data": {"items": cases, "count": len(cases), "query": q, "include_archived": include_archived}})

    def _update_case(self, uid, cid, data):
        if not isinstance(data, dict):
            raise ValueError("بدنه درخواست باید یک شیء JSON باشد.")
        allowed = {"name", "stage", "priority", "next_action"}
        unknown = set(data) - allowed
        if unknown:
            raise ValueError("فیلد نامعتبر در درخواست پرونده وجود دارد.")
        case = CaseService().update(
            uid, cid,
            name=data.get("name"), stage=data.get("stage"),
            priority=data.get("priority"), next_action=data.get("next_action"),
        )
        return self._send(200, {"ok": True, "data": {"case": case}})

    def _case_action(self, uid, cid, action):
        service = CaseService()
        if action == "archive":
            ok = service.archive(uid, cid)
            if not ok:
                raise CaseValidationError("پرونده قابل بایگانی نیست یا پیدا نشد.")
        else:
            ok = service.restore(uid, cid)
            if not ok:
                raise CaseValidationError("پرونده بایگانی‌شده پیدا نشد.")
        case = service.get(uid, cid)
        return self._send(200, {"ok": True, "data": {"case": case}})

    def _create_case(self, uid, data):
        if not isinstance(data, dict):
            raise ValueError("بدنه درخواست باید یک شیء JSON باشد.")
        from .core.entitlements import EntitlementService

        entitlement = EntitlementService()
        ok, reservation = entitlement.reserve(uid, "case", metadata={"source": "miniapp_api"})
        if not ok:
            message = "سهمیه پرونده کافی نیست." if reservation == "insufficient" else str(reservation)
            return self._error(409, "quota_exceeded", message)
        try:
            case = CaseService().create_empty(
                uid, str(data.get("name", "")),
                stage=data.get("stage", "new"),
                priority=data.get("priority", "normal"),
                next_action=data.get("next_action", ""),
            )
            if not entitlement.commit(uid, reservation):
                raise RuntimeError("ثبت نهایی سهمیه پرونده انجام نشد.")
            return self._send(201, {"ok": True, "data": {"case": case}})
        except Exception:
            try:
                entitlement.refund(uid, reservation)
            except Exception:
                log.exception("failed to refund case reservation user=%s", uid)
            raise

    def _timeline(self, uid, cid):
        if not CaseService().get(uid, cid):
            raise ProductCaseError("پرونده پیدا نشد.")
        query = parse_qs(urlparse(self.path).query)
        include_undated = query.get("undated", ["1"])[0].lower() not in {"0", "false", "no"}
        status = (query.get("status", [""])[0] or "").strip().lower()
        event_type = (query.get("type", [""])[0] or "").strip().lower()
        allowed_status = {"", "verified", "party_assertion", "uncertain", "conflict", "inferred", "undated"}
        allowed_types = {"", "filing", "service", "hearing", "judgment", "appeal", "execution", "contract", "amendment", "breach", "termination", "payment", "delivery", "notice", "inspection", "other"}
        if status not in allowed_status:
            raise ValueError("وضعیت Timeline نامعتبر است.")
        if event_type not in allowed_types:
            raise ValueError("نوع رویداد Timeline نامعتبر است.")
        data = build_case_chronology(uid, cid, include_undated=True)
        all_events = list(data.get("events") or [])
        filtered = [e for e in all_events if (include_undated or (e.get("date") or {}).get("gregorian_date"))]
        if status:
            filtered = [e for e in filtered if e.get("status") == status]
        if event_type:
            filtered = [e for e in filtered if e.get("event_type") == event_type]
        data["events"] = filtered
        data["filters"] = {"undated": include_undated, "status": status or None, "type": event_type or None}
        data["filtered_counts"] = {"events": len(filtered), "dated": sum(bool((e.get("date") or {}).get("gregorian_date")) for e in filtered), "undated": sum(not bool((e.get("date") or {}).get("gregorian_date")) for e in filtered), "conflicts": sum(e.get("status") == "conflict" for e in filtered)}
        return self._send(200, {"ok": True, "data": data})

    def _evidence(self, uid, cid):
        if not CaseService().get(uid, cid):
            raise ProductCaseError("پرونده پیدا نشد.")
        query = parse_qs(urlparse(self.path).query)
        status = (query.get("status", [""])[0] or "").strip().lower()
        allowed = {"", "supported", "contradicted", "mixed", "unverified", "unsupported"}
        if status not in allowed:
            raise ValueError("وضعیت Evidence نامعتبر است.")
        data = build_evidence_matrix(uid, cid)
        if status:
            claims = [c for c in data.get("claims", []) if c.get("claim_status") == status]
            wanted = {c.get("claim_id") for c in claims}
            matrix = [m for m in data.get("matrix", []) if m.get("claim_id") in wanted]
            data["claims"] = claims
            data["matrix"] = matrix
            counts = dict(data.get("counts") or {})
            counts["claims"] = len(claims)
            counts["supported"] = sum(c.get("claim_status") == "supported" for c in claims)
            counts["mixed"] = sum(c.get("claim_status") == "mixed" for c in claims)
            counts["contradicted"] = sum(c.get("claim_status") == "contradicted" for c in claims)
            counts["unsupported"] = sum(c.get("claim_status") == "unsupported" for c in claims)
            counts["unverified"] = sum(c.get("claim_status") == "unverified" for c in claims)
            counts["evidence_gaps"] = sum(bool(m.get("evidence_gap")) for m in matrix)
            data["counts"] = counts
        data["filters"] = {"status": status or None}
        return self._send(200, {"ok": True, "data": data})

    def _documents(self, uid, cid):
        service = DocumentService()
        case = CaseService().get(uid, cid)
        if not case:
            raise DocumentValidationError("پرونده پیدا نشد.")
        docs = service.public_list(uid, cid)
        saved_ids = set(db.list_saved_document_ids(uid, cid))
        for item in docs:
            item["saved"] = int(item.get("id") or 0) in saved_ids
        return self._send(200, {
            "ok": True,
            "data": {
                "items": docs,
                "count": len(docs),
                "max_file_mb": MAX_FILE_MB,
                "max_files_per_upload": MAX_CASE_ADDITION_FILES,
            },
        })

    def _saved_documents(self, uid):
        query = parse_qs(urlparse(self.path).query)
        try:
            limit = int((query.get("limit") or [30])[0])
        except (TypeError, ValueError):
            limit = 30
        items = db.list_saved_documents(uid, limit)
        return self._send(200, {"ok": True, "data": {"items": items}})

    def _search_case_documents(self, uid, cid):
        """Search extracted text in documents belonging to this user's case."""
        if not CaseService().get(uid, cid):
            raise DocumentValidationError("پرونده پیدا نشد.")
        query = (parse_qs(urlparse(self.path).query).get("q", [""])[0] or "").strip()
        if not query:
            raise ValueError("عبارت جست‌وجو را وارد کنید.")
        if len(query) > 200:
            raise ValueError("عبارت جست‌وجو نباید بیشتر از ۲۰۰ نویسه باشد.")
        # DocumentService.list uses the repository's case+owner join. Never
        # accept document IDs or arbitrary scope from the client.
        documents = DocumentService().list(uid, cid)
        hits = search_case_documents(documents, query, max_results=60, max_results_per_document=12)
        source_ids = {hit.get("document_id") for hit in hits}
        searchable_count = sum(bool((doc.get("extracted_text") or "").strip()) for doc in documents)
        return self._send(200, {
            "ok": True,
            "data": {
                "query": query,
                "items": hits,
                "count": len(hits),
                "matched_document_count": len(source_ids),
                "document_count": len(documents),
                "searchable_document_count": searchable_count,
                "coverage_note": "جست‌وجو فقط متن استخراج‌شده را پوشش می‌دهد؛ اسناد اسکن‌شده یا فاقد متن قابل‌استخراج ممکن است در نتایج نباشند.",
                "verification_note": "نتیجه، محل تطبیق در متن استخراج‌شده را نشان می‌دهد و جایگزین بررسی اصل سند نیست.",
            },
        })

    def _analyze_case_documents(self, uid, cid):
        """Analyze only documents belonging to this authenticated user's case."""
        if not CaseService().get(uid, cid):
            raise DocumentValidationError("پرونده پیدا نشد.")
        # Never accept document IDs or a client-supplied scope. The repository
        # query is constrained by both authenticated owner and case ID.
        documents = DocumentService().list(uid, cid)
        result = analyze_case_documents(documents)
        result["review_table"] = build_review_table(documents)
        result["case_id"] = cid
        result["coverage_note"] = "تحلیل فقط متن استخراج‌شده را پوشش می‌دهد؛ اسناد اسکن‌شده یا فاقد متن در بخش اسناد نیازمند OCR/استخراج هستند."
        return self._send(200, {"ok": True, "data": result})

    def _lawyer_preferences_schema(self, uid):
        # uid is derived only by the authenticated Telegram initData dispatcher.
        loaded = lawyer_pref_service.load_editor(uid)
        schema = dict(loaded["schema"])
        schema["persistence_enabled"] = True
        schema["stage"] = "3_of_6"
        schema["profile"] = loaded["profile"]
        return self._send(200, {"ok": True, "data": schema})

    def _lawyer_preferences_history(self, uid):
        q = parse_qs(urlparse(self.path).query)
        try:
            limit = int(q.get("limit", ["20"])[0])
        except (TypeError, ValueError):
            limit = 20
        items = lawyer_pref_service.list_history(uid, limit=limit)
        # Keep the existing snapshot payload while adding lightweight UI metadata.
        for item in items:
            item["selected_count"] = sum(
                len(fields) for fields in (item.get("preferences") or {}).values()
                if isinstance(fields, dict)
            )
        return self._send(200, {"ok": True, "data": {"items": items, "count": len(items), "limit": max(1, min(50, limit))}})

    def _lawyer_preferences_status_action(self, uid, action, data):
        target_status = "active" if action == "activate" else "inactive"
        result = lawyer_pref_service.change_editor_status(uid, data, target_status)
        return self._send(200, {"ok": True, "data": result})

    def _lawyer_preferences_restore_action(self, uid, data):
        result = lawyer_pref_service.restore_editor_version(uid, data)
        return self._send(200, {"ok": True, "data": result})

    def _lawyer_preferences_action(self, uid, action, data):
        if not isinstance(data, dict):
            raise ValueError("بدنه درخواست باید یک شیء JSON باشد.")
        if action == "suggest":
            suggestion = suggest_from_feedback(data.get("signal"))
            return self._send(200, {"ok": True, "data": {"suggestion": suggestion}})
        if action == "preview":
            result = lawyer_pref_service.preview_editor(data.get("preferences") or {})
            result.update({"lawyer_confirmed_for_preview": data.get("lawyer_confirmed") is True,
                           "notice": "پیش‌نمایش انجام شد؛ برای ذخیره دائمی باید دکمه ذخیره را جداگانه تأیید کنید."})
            return self._send(200, {"ok": True, "data": result})
        if action == "save":
            result = lawyer_pref_service.save_editor(uid, data)
            return self._send(200, {"ok": True, "data": result})
        raise ValueError("عملیات ترجیحات معتبر نیست.")

    def _get_case_workflow_agent(self, uid, cid):
        if not CaseService().get(uid, cid):
            raise DocumentValidationError("پرونده پیدا نشد.")
        session = db.get_case_workflow_agent_session(uid, cid)
        if not session:
            return self._send(200, {"ok": True, "data": {"exists": False, "case_id": cid}})
        state = session.get("state") or {}
        return self._send(200, {"ok": True, "data": {"exists": True, "state": state, "summary": workflow_summary(state), "updated_at": session.get("updated_at")}})

    def _case_workflow_agent_action(self, uid, cid, action, data):
        if not isinstance(data, dict):
            raise ValueError("بدنه درخواست باید یک شیء JSON باشد.")
        case = CaseService().get(uid, cid)
        if not case:
            raise DocumentValidationError("پرونده پیدا نشد.")
        if case.get("status") == "archived":
            raise DocumentValidationError("گردش کار پرونده بایگانی‌شده قابل اجرا نیست.")
        session = db.get_case_workflow_agent_session(uid, cid)
        expected_updated_at = (session or {}).get("updated_at")
        state = (session or {}).get("state") or {}
        now_event = lambda kind, detail: {"type": kind, "detail": detail, "at": db.now_iso()}
        if action == "start":
            if state and state.get("status") not in {"COMPLETED", "CANCELLED"}:
                return self._send(200, {"ok": True, "data": {"state": state, "summary": workflow_summary(state), "existing": True}})
            query = str(data.get("query") or "").strip()
            if len(query) > 300:
                raise ValueError("عبارت جست‌وجو نباید بیشتر از ۳۰۰ نویسه باشد.")
            state = create_case_workflow(cid, query)
            state["history"] = [now_event("created", "گردش کار توسط وکیل ایجاد شد.")]
        elif action == "approve":
            if not state:
                raise ValueError("ابتدا گردش کار را ایجاد کنید.")
            step = str(data.get("step") or "")
            approved = data.get("approved")
            if not isinstance(approved, bool):
                raise ValueError("وضعیت تأیید باید مشخص باشد.")
            state = approve_step(state, step, approved=approved)
            state.setdefault("history", []).append(now_event("approved" if approved else "declined", step))
        elif action == "run":
            if not state:
                raise ValueError("گردش کاری برای اجرا وجود ندارد.")
            # Documents are loaded only after ownership of this exact case is verified.
            documents = DocumentService().list(uid, cid)
            step = str(state.get("current_step") or "")
            state = run_approved_step(state, documents)
            state.setdefault("history", []).append(now_event("step_executed", step))
        else:
            raise ValueError("عملیات گردش کار معتبر نیست.")
        state["history"] = list(state.get("history") or [])[-100:]
        saved = db.save_case_workflow_agent_session_if_unchanged(
            uid, cid, state, workflow_version=1, expected_updated_at=expected_updated_at
        )
        if saved is None:
            return self._error(
                409, "workflow_state_conflict",
                "وضعیت گردش کار هم‌زمان تغییر کرده است. صفحه را تازه‌سازی کنید و دوباره اقدام کنید."
            )
        saved_state = (saved or {}).get("state") or state
        return self._send(200, {"ok": True, "data": {"state": saved_state, "summary": workflow_summary(saved_state), "updated_at": (saved or {}).get("updated_at")}})

    def _upload_documents(self, uid, cid):
        content_type = self.headers.get("Content-Type", "")
        if not content_type.lower().startswith("multipart/form-data"):
            raise ValueError("آپلود سند باید با multipart/form-data انجام شود.")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        # The request is buffered before multipart parsing, so enforce a strict
        # aggregate limit in addition to the per-file and file-count limits.
        max_request = MAX_UPLOAD_REQUEST_MB * 1024 * 1024
        if length <= 0 or length > max_request:
            raise ValueError(
                f"حجم کل آپلود نباید بیشتر از {MAX_UPLOAD_REQUEST_MB}MB باشد. "
                "برای فایل‌های بزرگ‌تر، اسناد را در چند نوبت ارسال کنید."
            )

        body = self.rfile.read(length)
        if len(body) != length:
            raise ValueError("بدنه آپلود ناقص دریافت شد.")
        tmp_paths = []
        fields = []
        try:
            mime_blob = (f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n").encode("utf-8") + body
            message = BytesParser(policy=policy.default).parsebytes(mime_blob)
            parts = message.walk() if message.is_multipart() else []
            for field in parts:
                disposition = field.get_content_disposition()
                name_value = field.get_filename()
                if disposition != "form-data" or not name_value:
                    continue
                name = Path(str(name_value)).name or "document"
                suffix = Path(name).suffix.lower()
                if suffix not in {".pdf", ".docx", ".txt", ".jpg", ".jpeg", ".png", ".webp"}:
                    raise DocumentValidationError("فرمت فایل پشتیبانی نمی‌شود. PDF، DOCX، TXT و تصویر مجاز است.")
                data = field.get_payload(decode=True) or b""
                if len(data) > MAX_FILE_MB * 1024 * 1024:
                    raise DocumentValidationError(f"حجم هر فایل نباید بیشتر از {MAX_FILE_MB}MB باشد.")
                if not data:
                    raise DocumentValidationError("فایل خالی قابل افزودن نیست.")
                fd, tmp = tempfile.mkstemp(prefix="legalbot-miniapp-", suffix=suffix)
                with os.fdopen(fd, "wb") as out:
                    out.write(data)
                tmp_paths.append(tmp)
                fields.append({"path": tmp, "name": name, "suffix": suffix})
            if not fields:
                raise DocumentValidationError("هیچ فایلی برای آپلود ارسال نشده است.")
            if len(fields) > MAX_CASE_ADDITION_FILES:
                raise DocumentValidationError(f"در هر نوبت حداکثر {MAX_CASE_ADDITION_FILES} فایل قابل افزودن است.")
            result = DocumentService().add_files(uid, cid, fields)
            safe_docs = DocumentService().public_list(uid, cid)
            result["documents"] = safe_docs
            return self._send(201, {"ok": True, "data": result})
        finally:
            for tmp in tmp_paths:
                try:
                    Path(tmp).unlink(missing_ok=True)
                except OSError:
                    pass

    def _workspace(self, uid, cid):
        query = parse_qs(urlparse(self.path).query)
        deep = query.get("deep", ["1"])[0].lower() not in {"0", "false", "no"}
        data = ProductCaseService().workspace(uid, cid, include_deep_intelligence=deep)
        return self._send(200, {"ok": True, "data": data})

    def _intelligence(self, uid, cid):
        query = parse_qs(urlparse(self.path).query)
        deep = query.get("deep", ["1"])[0].lower() not in {"0", "false", "no"}
        data = ProductCaseService().workspace(uid, cid, include_deep_intelligence=deep)
        intelligence = data.get("intelligence") or {}
        return self._send(200, {
            "ok": True,
            "data": {
                "contract_version": data.get("contract_version"),
                "case": data.get("case"),
                "intelligence": intelligence,
            },
        })

    def _ai_history(self, uid, cid):
        query = parse_qs(urlparse(self.path).query)
        try:
            limit = max(1, min(int(query.get("limit", [5])[0]), 80))
        except ValueError:
            limit = 5
        data = ProductCaseService().ai_history(uid, cid, limit)
        return self._send(200, {"ok": True, "data": {"items": data, "count": len(data)}})

    def _ask_ai(self, uid, cid, data):
        if not isinstance(data, dict):
            raise ValueError("بدنه درخواست باید یک شیء JSON باشد.")
        result = ProductCaseService().ask_ai(
            uid,
            cid,
            str(data.get("question") or ""),
            context_mode=str(data.get("context_mode") or "full"),
        )
        return self._send(200, {"ok": True, "data": result})

    def _draft_intake(self, uid, cid):
        case = db.get_case(uid, cid)
        if not case:
            return self._error(404, "case_not_found", "پرونده پیدا نشد یا دسترسی به آن وجود ندارد.")
        if str(case.get("status") or "").lower() == "archived":
            return self._send(200, {"ok": True, "data": {"status": "CASE_ARCHIVED", "brief_type": "لایحه دفاعیه", "answers": {}, "questions": []}})
        state = load_workflow_state(uid, cid)
        if state.get("status") != "WAITING_FOR_INPUT":
            return self._send(200, {"ok": True, "data": {"status": state.get("status") or "NOT_STARTED", "brief_type": state.get("brief_type") or "لایحه دفاعیه", "answers": state.get("answers") or {}, "questions": [], "preflight": state.get("preflight") or {}}})
        answers = state.get("answers") or {}
        deferred = set(state.get("deferred") or [])
        preflight = preflight_v150(uid, cid, state.get("brief_type") or "لایحه دفاعیه", answers, deferred)
        return self._send(200, {"ok": True, "data": {"status": "WAITING_FOR_INPUT", "brief_type": state.get("brief_type") or "لایحه دفاعیه", "answers": answers, "deferred": sorted(deferred), "preflight": preflight, "questions": preflight.get("questions") or preflight.get("workflow_required_missing") or []}})

    def _lawyer_library(self, uid):
        query = parse_qs(urlparse(self.path).query)
        kind = (query.get("kind", [""])[0] or "")[:20]
        term = (query.get("q", [""])[0] or "")[:120]
        items = list_lawyer_library(uid, kind=kind, query=term)
        return self._send(200, {"ok": True, "data": {"items": items, "count": len(items)}})

    def _work_products(self, uid):
        query = parse_qs(urlparse(self.path).query)
        term = (query.get("q", [""])[0] or "")[:120]
        saved_only = query.get("saved", ["0"])[0].lower() in {"1", "true", "yes"}
        try:
            limit = max(1, min(int(query.get("limit", [40])[0]), 80))
        except ValueError:
            limit = 40
        items = list_work_products(uid, limit=limit, query=term, saved_only=saved_only)
        return self._send(200, {"ok": True, "data": {"items": items, "count": len(items)}})

    def _drafts(self, uid, cid):
        items = list_draft_artifacts(uid, cid, limit=20)
        latest = items[0] if items else None
        return self._send(200, {"ok": True, "data": {"items": items, "latest": latest}})

    def _draft_artifact(self, uid, cid, artifact_id):
        item = get_draft_artifact(uid, cid, str(artifact_id))
        if not item:
            return self._error(404, "draft_not_found", "نسخه پیش‌نویس پیدا نشد.")
        return self._send(200, {"ok": True, "data": item})

    def _draft_reviews(self, uid, cid, artifact_id):
        if not get_draft_artifact(uid, cid, str(artifact_id)):
            return self._error(404, "draft_not_found", "نسخه پیش‌نویس پیدا نشد.")
        return self._send(200, {"ok": True, "data": {"items": list_draft_reviews(uid, cid, str(artifact_id))}})

    def _record_draft_review(self, uid, cid, artifact_id, data):
        if not isinstance(data, dict):
            raise ValueError("بدنه درخواست باید یک شیء JSON باشد.")
        try:
            event = record_draft_review(
                uid, cid, artifact_id,
                decision=data.get("decision"),
                note=data.get("note", ""),
                confirm_review=data.get("confirm_review") is True,
            )
        except ValueError as exc:
            code = str(exc)
            if code == "draft_not_found":
                return self._error(404, "draft_not_found", "نسخه پیش‌نویس پیدا نشد.")
            if code == "case_not_found":
                return self._error(404, "case_not_found", "پرونده پیدا نشد.")
            if code == "case_archived":
                return self._error(409, "case_archived", "برای پرونده بایگانی‌شده امکان ثبت بازبینی نیست.")
            if code == "review_note_too_long":
                return self._error(400, "review_note_too_long", "یادداشت بازبینی نباید بیش از ۸۰۰۰ نویسه باشد.")
            if code == "review_confirmation_required":
                return self._error(400, "review_confirmation_required", "برای ثبت نتیجه، تأیید صریح بازبینی الزامی است.")
            if code == "review_decision_invalid":
                return self._error(400, "review_decision_invalid", "نتیجه بازبینی نامعتبر است.")
            raise
        return self._send(201, {"ok": True, "data": {"review": event}})

    def _draft(self, uid, cid, data):
        if not isinstance(data, dict):
            raise ValueError("بدنه درخواست باید یک شیء JSON باشد.")
        answers = data.get("answers", {})
        if not isinstance(answers, dict):
            return self._error(400, "draft_answers_invalid", "پاسخ‌های تکمیلی باید به‌صورت یک شیء معتبر ارسال شوند.")
        if len(answers) > 12 or any(not isinstance(k, str) or len(k) > 120 or not isinstance(v, str) or len(v) > 3000 for k, v in answers.items()):
            return self._error(400, "draft_answers_invalid", "حداکثر ۱۲ پاسخ متنی و حداکثر ۳۰۰۰ نویسه برای هر پاسخ مجاز است.")
        result = ProductCaseService().run_draft(
            uid,
            cid,
            brief_type=str(data.get("brief_type") or "لایحه دفاعیه"),
            answers=answers,
            deferred=set(data.get("deferred") or []) if isinstance(data.get("deferred"), list) else set(),
            allow_incomplete=bool(data.get("allow_incomplete", False)),
        )
        return self._send(200, {"ok": True, "data": result})


def create_server(host: str = API_HOST, port: int = API_PORT):
    if API_ENV in {"prod", "production"}:
        if not BOT_TOKEN:
            raise RuntimeError("BOT_TOKEN is required in production.")
        if API_ALLOWED_ORIGIN == "*" or not API_ALLOWED_ORIGIN.startswith("https://"):
            raise RuntimeError("API_ALLOWED_ORIGIN must be a specific HTTPS origin in production.")
        if not MINIAPP_URL or not MINIAPP_URL.startswith("https://"):
            raise RuntimeError("MINIAPP_URL must be a public HTTPS URL in production.")
        if API_DEV_MODE:
            raise RuntimeError("API_DEV_MODE must be disabled in production.")
    # API and Telegram entrypoints share the same SQLite database/schema.
    init_db(); v193_upgrade(); v20_upgrade(); v67_upgrade()
    init_case_workspace_tables(); init_case_dates_table(); init_case_reminders_table(); init_drafting_workflow_tables(); init_case_workflow_agent_tables(); init_drafting_artifact_tables(); init_work_product_bookmarks(); init_lawyer_library(); init_lawyer_workflows()
    return ThreadingHTTPServer((host, port), APIHandler)


def serve(host: str = API_HOST, port: int = API_PORT):
    server = create_server(host, port)
    log.info("LegalBot API listening on %s:%s", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    serve()
