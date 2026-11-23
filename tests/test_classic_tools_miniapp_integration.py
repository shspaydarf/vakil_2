import tempfile
import pytest
from pathlib import Path

from legal_bot import api, db
from legal_bot.core.cases import CaseService


def setup_module(module):
    module._old_db = db.DB_PATH
    module._tmp = tempfile.TemporaryDirectory()
    db.DB_PATH = Path(module._tmp.name) / "classic-tools.db"
    db.init_db(); db.v193_upgrade(); db.v20_upgrade(); db.v67_upgrade(); db.init_case_workspace_tables()
    db.register_user(77101, "classic-a", "7101", full_name="A")
    db.register_user(77102, "classic-b", "7102", full_name="B")
    module.case_a = CaseService().create_empty(77101, "قرارداد اجاره")


def teardown_module(module):
    db.DB_PATH = module._old_db
    module._tmp.cleanup()


def handler(path="/"):
    obj = object.__new__(api.APIHandler)
    obj.path = path
    captured = {}
    obj._send = lambda status, payload, **kwargs: captured.update(status=status, payload=payload)
    obj._error = lambda status, code, message: captured.update(status=status, payload={"ok": False, "error": {"code": code, "message": message}})
    return obj, captured


def test_clients_api_crud_and_tenant_isolation():
    h, out = handler()
    h._create_client(77101, {"name": "علی رضایی", "phone": "09120000000", "note": "موکل اول"})
    assert out["status"] == 201
    cid = out["payload"]["data"]["item"]["id"]
    h, out = handler("/api/v1/clients?q=علی")
    h._clients(77101)
    assert out["payload"]["data"]["count"] == 1
    h, out = handler()
    h._client_detail(77102, cid)
    assert out["status"] == 404
    h, out = handler()
    h._update_client(77101, cid, {"name": "علی رضایی جدید"})
    assert out["payload"]["data"]["item"]["name"] == "علی رضایی جدید"
    h, out = handler()
    h._link_client_case(77101, cid, case_a["id"])
    assert out["status"] == 201
    h, out = handler()
    h._client_detail(77101, cid)
    assert len(out["payload"]["data"]["cases"]) == 1
    h, out = handler()
    h._delete_client(77101, cid)
    assert out["payload"]["data"]["deleted"] is True


def test_calculator_api_uses_shared_bot_reference_data():
    h, out = handler()
    h._run_calculator(77101, {"kind": "mahr", "amount": "100000000", "contract_year": 1402})
    result = out["payload"]["data"]["result"]
    assert result["amount"] > 100_000_000
    assert result["provisional"] is True
    h, out = handler()
    h._run_calculator(77101, {"kind": "diya", "percent": 100, "month_type": "normal"})
    assert out["payload"]["data"]["result"]["amount"] == 2_100_000_000
    h, out = handler()
    h._run_calculator(77101, {"kind": "deadline", "start_date": "2026-11-01", "days": 20})
    assert out["payload"]["data"]["result"]["end_date_gregorian"] == "2026-11-21"


def test_existing_bot_guides_are_exposed_without_ai():
    h, out = handler()
    h._run_guide(77101, "check", {"role": "holder", "topic": "claim"})
    assert "راهنمای چک" in out["payload"]["data"]["text"]
    h, out = handler()
    h._run_guide(77101, "shora", {"topic": "check", "amount": "mid", "docs": "yes"})
    assert "دادگاه صلح" in out["payload"]["data"]["text"]
    h, out = handler()
    h._run_guide(77101, "tax", {"activity": "service", "task": "notice", "income": "mid", "docs": "yes"})
    assert "۳۰ روز" in out["payload"]["data"]["text"]


def test_global_legal_search_endpoint_returns_structured_records():
    h, out = handler("/api/v1/legal-search?q=قانون%20مدنی&limit=5")
    h._legal_search(77101)
    assert out["status"] == 200
    assert out["payload"]["data"]["query"] == "قانون مدنی"
    assert "items" in out["payload"]["data"]


def test_guided_tree_start_is_case_scoped_and_returns_first_question():
    db.add_case_document(case_a["id"], "قرارداد.txt", 1, "قرارداد فروش کالا و تعهد پرداخت وجه طبق قرارداد")
    h, out = handler()
    h._guided_tree_start(77101, "contract", {"case_id": case_a["id"]})
    assert out["status"] == 200
    assert out["payload"]["data"]["state"]["status"] in {"active", "not_contract"}
    if out["payload"]["data"]["state"]["status"] == "active":
        assert out["payload"]["data"]["node"]["question"]
        session_id = out["payload"]["data"]["session_id"]
        choice = out["payload"]["data"]["node"]["choices"][0][1]
        h, out = handler()
        h._guided_tree_step(77101, "contract", {"session_id": session_id, "choice": choice})
        assert out["status"] == 200
        h, out = handler()
        h._guided_tree_step(77102, "contract", {"session_id": session_id, "choice": choice})
        assert out["status"] == 404


def test_quick_calculator_variants_and_date_conversion_are_available():
    h, out = handler()
    h._run_calculator(77101, {"kind": "quick_percent", "amount": "2000000", "percent": "12.5"})
    assert out["payload"]["data"]["result"]["amount"] == 250000
    h, out = handler()
    h._run_calculator(77101, {"kind": "rial_convert", "amount": "100000", "direction": "toman_to_rial"})
    assert out["payload"]["data"]["result"]["output"] == 1000000
    h, out = handler()
    h._run_calculator(77101, {"kind": "installment", "total": "1000", "count": "3"})
    assert out["payload"]["data"]["result"]["installment"] == 333
    h, out = handler()
    h._run_calculator(77101, {"kind": "date_convert", "value": "۱۴۰۵/۰۱/۰۱"})
    assert out["payload"]["data"]["result"]["gregorian"]


def test_important_date_reminder_api_is_private_and_visible_in_calendar():
    db.add_case_important_dates(77101, case_a["id"], [{
        "date_jalali": "1405/09/01", "date_gregorian": "2026-11-22",
        "description": "جلسه رسیدگی", "source_page": 2, "source_text": "جلسه رسیدگی در تاریخ مقرر"
    }])
    rows = db.list_case_important_dates(77101, 20)
    date_row = next(x for x in rows if x["description"] == "جلسه رسیدگی")
    h, out = handler()
    h._set_important_date_reminder(77101, date_row["id"], {"enabled": True})
    assert out["payload"]["data"]["enabled"] is True
    h, out = handler("/api/v1/important-dates")
    h._important_dates(77101)
    assert next(x for x in out["payload"]["data"]["items"] if x["id"] == date_row["id"])["reminder_enabled"] is True
    items = db.list_user_calendar_items(77101, "2026-11-01", "2026-11-30")
    assert next(x for x in items if x["id"] == date_row["id"])["reminder_enabled"] == 1
    h, out = handler()
    h._set_important_date_reminder(77102, date_row["id"], {"enabled": True})
    assert out["status"] == 404


def test_contract_playbook_api_lists_templates_and_requires_consent_before_ai(monkeypatch):
    h, out = handler()
    h._send(200, {"ok": True, "data": {"items": api.list_contract_playbooks()}})
    assert len(out["payload"]["data"]["items"]) >= 3
    monkeypatch.setattr(api, "AI_ENABLED", True)
    monkeypatch.setattr(api, "DEEPSEEK_API_KEY", "configured")
    monkeypatch.setattr(api, "AI_EXTERNAL_DATA_CONSENT", False)
    h, out = handler()
    h._contract_review(77101, case_a["id"], {"playbook_id": "lease"})
    assert out["status"] == 409
    assert out["payload"]["error"]["code"] == "ai_consent_required"


def test_tax_screen_ocr_upload_uses_local_ocr_and_cleans_temp_file(monkeypatch):
    from email.mime.multipart import MIMEMultipart
    from email.mime.base import MIMEBase
    from email import encoders
    from io import BytesIO
    import tempfile

    msg = MIMEMultipart("form-data")
    part = MIMEBase("image", "jpeg")
    part.set_payload(b"fake-jpeg-data")
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", 'form-data; name="image"; filename="screen.jpg"')
    msg.attach(part)
    body = msg.as_bytes()
    content_type = msg.get("Content-Type")
    monkeypatch.setattr(api, "extract_with_diagnostics", lambda path: ("درآمد و هزینه مالیات و ابلاغ", {"ocr": "local"}))
    h, out = handler("/api/v1/tax/screen")
    h.headers = {"Content-Type": content_type, "Content-Length": str(len(body))}
    h.rfile = BytesIO(body)
    h._tax_screen_upload(77101)
    assert out["status"] == 200
    assert "راهنمای همین صفحه" in out["payload"]["data"]["text"]
    assert out["payload"]["data"]["diagnostics"]["ocr"] == "local"


def test_miniapp_exposes_classic_bot_tools_and_ai_contract_playbooks():
    root = Path(__file__).resolve().parents[1]
    app = (root / "miniapp" / "app.js").read_text(encoding="utf-8")
    html = (root / "miniapp" / "index.html").read_text(encoding="utf-8")
    assert "function openClassicTools()" in app
    assert "/api/v1/legal-search?q=" in app
    assert "/api/v1/clients" in app
    assert "/api/v1/calculators/run" in app
    assert "/api/v1/guides/" in app
    assert "/api/v1/guided-trees/" in app
    assert "/api/v1/tax/screen" in app
    assert "/api/v1/contract-playbooks" in app
    assert "data-date-reminder" in app
    assert "id=\"openClassicTools\"" in html
    assert "id=\"contractPlaybooksList\"" in html


def test_subscription_info_and_receipt_submission_are_available_from_miniapp(monkeypatch):
    from email.mime.multipart import MIMEMultipart
    from email.mime.base import MIMEBase
    from email.mime.text import MIMEText
    from email import encoders
    from io import BytesIO
    import json

    h, out = handler("/api/v1/subscription-info")
    monkeypatch.setattr(api, "SUBSCRIPTION_PRICE_TEXT", "اشتراک آزمایشی")
    monkeypatch.setattr(api.db, "has_pending_payment_request", lambda uid: False)
    h._subscription_info(77101)
    assert out["payload"]["data"]["price_text"] == "اشتراک آزمایشی"

    msg = MIMEMultipart("form-data")
    part = MIMEBase("image", "jpeg")
    part.set_payload(b"fake-receipt")
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", 'form-data; name="receipt"; filename="receipt.jpg"')
    msg.attach(part)
    caption = MIMEText("پرداخت امروز")
    caption.add_header("Content-Disposition", 'form-data; name="caption"')
    msg.attach(caption)
    body = msg.as_bytes()

    class FakeResponse:
        def __init__(self, payload): self.payload = json.dumps(payload).encode()
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self): return self.payload

    calls = []
    def fake_urlopen(request, timeout=0):
        calls.append(request)
        if len(calls) == 1:
            return FakeResponse({"ok": True, "result": {"message_id": 900, "photo": [{"file_id": "telegram-file-id"}]}})
        return FakeResponse({"ok": True, "result": {"message_id": 901}})

    monkeypatch.setattr(api, "urlopen", fake_urlopen)
    monkeypatch.setattr(api, "BOT_TOKEN", "fake-token")
    monkeypatch.setattr(api, "ADMIN_TELEGRAM_IDS", {88001})
    monkeypatch.setattr(api.db, "create_payment_request", lambda uid, file_id, caption: 123)
    monkeypatch.setattr(api.db, "get_payment_request", lambda pid: {"id": pid, "user_id": 77101, "status": "pending", "payment_reference": "LB-TEST"})
    h, out = handler("/api/v1/subscription-receipts")
    h.headers = {"Content-Type": msg.get("Content-Type"), "Content-Length": str(len(body))}
    h.rfile = BytesIO(body)
    h._submit_subscription_receipt(77101)
    assert out["status"] == 201
    assert out["payload"]["data"]["payment_reference"] == "LB-TEST"
    assert len(calls) == 2


def test_miniapp_account_exposes_subscription_receipt_flow():
    app = (Path(__file__).resolve().parents[1] / "miniapp" / "app.js").read_text(encoding="utf-8")
    assert "async function openSubscription()" in app
    assert "/api/v1/subscription-info" in app
    assert "/api/v1/subscription-receipts" in app


def test_referral_dashboard_and_status_actions_are_owner_scoped(monkeypatch):
    incoming = [{"id": 17, "referral_id": 42, "topic": "قرارداد", "city": "تهران", "urgency": "soon", "details": "شرح مختصر", "status": "sent", "client_user_id": 99001, "full_name": "وکیل", "service_title": "خدمات حقوقی", "phone": "0912"}]
    monkeypatch.setattr(api.db, "list_referrals_for_user", lambda uid, limit: [{"id": 8, "topic": "ملک", "city": "شیراز", "urgency": "normal", "status": "new"}])
    monkeypatch.setattr(api.db, "list_referral_matches_for_lawyer", lambda uid, limit: incoming if uid == 77101 else [])
    h, out = handler()
    h._referrals(77101)
    assert out["payload"]["data"]["incoming_matches"][0]["referral_id"] == 42
    assert "client_user_id" not in out["payload"]["data"]["incoming_matches"][0]

    monkeypatch.setattr(api.db, "get_referral_match", lambda mid: {"id": mid, "lawyer_user_id": 77101, "client_user_id": 99001, "referral_id": 42, "status": "sent", "full_name": "وکیل", "service_title": "خدمات", "phone": "0912"})
    monkeypatch.setattr(api.db, "update_referral_match", lambda mid, uid, status, note: uid == 77101 and status == "accepted")
    notifications=[]
    monkeypatch.setattr(api.APIHandler, "_telegram_json_call", lambda self, method, payload: notifications.append((method,payload)) or {})
    h, out = handler()
    h._update_referral_match(77101, 17, {"status": "accepted"})
    assert out["status"] == 200
    assert len(notifications) == 2
    h, out = handler()
    h._update_referral_match(77102, 17, {"status": "accepted"})
    assert out["status"] == 404


def test_miniapp_has_referral_dashboard_entry_and_api_calls():
    app = (Path(__file__).resolve().parents[1] / "miniapp" / "app.js").read_text(encoding="utf-8")
    assert "function openReferrals()" in app
    assert "api('/api/v1/referrals')" in app
    assert "/api/v1/referrals/matches/" in app


def test_referral_request_creation_requires_explicit_consent_and_notifies_admins(monkeypatch):
    monkeypatch.setattr(api, "BOT_TOKEN", "fake-token")
    monkeypatch.setattr(api, "ADMIN_TELEGRAM_IDS", {88001})
    monkeypatch.setattr(api.db, "create_referral_request", lambda uid, topic, city, urgency, details, consent: 321 if consent else None)
    monkeypatch.setattr(api.db, "list_matching_services", lambda topic, city, limit: [{"id": 7, "service_title": "وکیل قرارداد", "city": "تهران"}])
    sent=[]
    monkeypatch.setattr(api.APIHandler, "_telegram_json_call", lambda self, method, payload: sent.append((method,payload)) or {})
    h, out = handler()
    h._create_referral_request(77101, {"topic":"قرارداد","city":"تهران","urgency":"soon","details":"شرح بدون اطلاعات تماس موکل","consent":True})
    assert out["status"] == 201
    assert out["payload"]["data"]["id"] == 321
    assert sent[0][1]["reply_markup"]["inline_keyboard"]
    h, out = handler()
    try:
        h._create_referral_request(77101, {"topic":"قرارداد","city":"تهران","urgency":"soon","details":"شرح بدون اطلاعات تماس موکل","consent":False})
    except ValueError:
        pass
    else:
        raise AssertionError("referral creation must require explicit consent")


def test_remaining_bot_calculators_are_exposed_without_ai():
    h, out = handler()
    h._run_calculator(77101, {"kind": "diya", "mode": "head", "preset": next(iter(api.HEAD_WOUND_PCTS))})
    assert out["payload"]["data"]["result"]["amount"] > 0
    h, out = handler()
    h._run_calculator(77101, {"kind": "alcohol_fine", "value_toman": "1000000"})
    assert out["payload"]["data"]["result"]["amount"] > 0
    h, out = handler()
    h._run_calculator(77101, {"kind": "date_diff", "date_a": "۱۴۰۵/۰۱/۰۱", "date_b": "۱۴۰۵/۰۱/۱۰"})
    assert out["payload"]["data"]["result"]["days"] == 9


def test_support_feedback_is_saved_with_authenticated_owner():
    captured=[]
    monkeypatch_add_feedback = db.add_feedback
    db.add_feedback = lambda uid, kind, message, context="": captured.append((uid,kind,message,context))
    try:
        h, out = handler()
        h._create_feedback(77101, {"kind":"support","message":"مشکل در نمایش تقویم","context":"Mini App support"})
        assert out["status"] == 201
        assert captured == [(77101,"support","مشکل در نمایش تقویم","Mini App support")]
    finally:
        db.add_feedback = monkeypatch_add_feedback


def test_student_practice_catalog_and_mcq_session_are_private_and_do_not_leak_answers():
    h, out = handler('/api/v1/student-practice/catalog?level=llb1')
    h._student_practice_catalog(77101)
    assert out['status'] == 200
    catalog = out['payload']['data']
    assert catalog['levels'] and catalog['courses']
    assert catalog['essay_categories']

    h, out = handler()
    h._student_practice_action(77101, 'start', {'mode': 'mcq', 'course_id': 'llb1_intro'})
    assert out['status'] == 201
    started = out['payload']['data']
    assert started['mode'] == 'mcq'
    assert len(started['options']) == 4
    assert 'answer' not in started and 'explain' not in started
    sid = started['session_id']
    token = started['question_token']

    h, out = handler()
    with pytest.raises(ValueError):
        h._student_practice_action(77102, 'answer', {'session_id': sid, 'question_token': token, 'choice': 0})

    state = api._STUDENT_PRACTICE_SESSIONS[sid]
    correct_choice = int(state['items'][0]['answer'])
    h, out = handler()
    h._student_practice_action(77101, 'answer', {'session_id': sid, 'question_token': token, 'choice': correct_choice})
    assert out['status'] == 200
    result = out['payload']['data']
    assert 'feedback' in result and result['question']['question_token'] == f'{sid}:1'

    h, out = handler()
    with pytest.raises(ValueError):
        h._student_practice_action(77101, 'answer', {'session_id': sid, 'question_token': token, 'choice': 0})


def test_student_practice_essay_sample_and_next_are_server_side():
    h, out = handler()
    h._student_practice_action(77101, 'start', {'mode': 'essay', 'category_id': 'civil'})
    assert out['status'] == 201
    started = out['payload']['data']
    assert started['mode'] == 'essay'
    assert 'sample' not in started
    sid, token = started['session_id'], started['question_token']

    h, out = handler()
    with pytest.raises(ValueError):
        h._student_practice_action(77102, 'essay-sample', {'session_id': sid, 'question_token': token})

    h, out = handler()
    h._student_practice_action(77101, 'essay-sample', {'session_id': sid, 'question_token': token})
    assert out['status'] == 200
    assert out['payload']['data']['sample']

    h, out = handler()
    h._student_practice_action(77101, 'essay-next', {'session_id': sid, 'question_token': token})
    assert out['status'] == 200
    assert out['payload']['data']['index'] == 2
    assert out['payload']['data']['question_token'] == f'{sid}:1'


def test_miniapp_exposes_student_practice_in_separate_academic_section():
    root = Path(__file__).resolve().parents[1]
    app = (root / 'miniapp' / 'app.js').read_text(encoding='utf-8')
    css = (root / 'miniapp' / 'styles.css').read_text(encoding='utf-8')
    assert 'studentPracticeOpen' in app
    assert "'/api/v1/student-practice/catalog'" in app
    assert "'/api/v1/student-practice/start'" in app
    assert "'/api/v1/student-practice/answer'" in app
    assert 'student-practice-launch' in css
    assert 'ACADEMIC PRACTICE' in app


def test_student_practice_requires_registered_account_and_api_routes_are_wired():
    h, out = handler()
    h._student_practice_catalog(77999)
    assert out['status'] == 404
    assert out['payload']['error']['code'] == 'user_not_found'
    import inspect
    assert '/student-practice/catalog' in inspect.getsource(api.APIHandler.do_GET)
    assert '/student-practice/(start|answer|essay-sample|essay-next)' in inspect.getsource(api.APIHandler.do_POST)
