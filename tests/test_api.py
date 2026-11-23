import hashlib
import hmac
import json
import time
from urllib.parse import urlencode


def _init_data(user_id, bot_token, auth_date=None):
    auth_date = auth_date or int(time.time())
    user = json.dumps({"id": user_id, "first_name": "Test"}, separators=(",", ":"))
    pairs = {"auth_date": str(auth_date), "query_id": "AA", "user": user}
    data_check = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    pairs["hash"] = digest
    return urlencode(pairs)


def test_telegram_init_data_validation(monkeypatch):
    from legal_bot import api
    monkeypatch.setattr(api, "BOT_TOKEN", "123456:TESTTOKEN")
    raw = _init_data(12345, api.BOT_TOKEN)
    assert api.telegram_user_id_from_init_data(raw) == 12345


def test_telegram_init_data_rejects_tampering(monkeypatch):
    from legal_bot import api
    monkeypatch.setattr(api, "BOT_TOKEN", "123456:TESTTOKEN")
    raw = _init_data(12345, api.BOT_TOKEN).replace("12345", "54321", 1)
    try:
        api.telegram_user_id_from_init_data(raw)
    except ValueError:
        pass
    else:
        raise AssertionError("tampered initData was accepted")

def test_telegram_init_data_rejects_expired(monkeypatch):
    from legal_bot import api
    monkeypatch.setattr(api, "BOT_TOKEN", "123456:TESTTOKEN")
    raw = _init_data(12345, api.BOT_TOKEN, auth_date=int(time.time()) - api.API_MAX_AUTH_AGE - 5)
    try:
        api.telegram_user_id_from_init_data(raw)
    except ValueError:
        pass
    else:
        raise AssertionError("expired initData was accepted")


def test_telegram_init_data_rejects_future_timestamp(monkeypatch):
    from legal_bot import api
    monkeypatch.setattr(api, "BOT_TOKEN", "123456:TESTTOKEN")
    raw = _init_data(12345, api.BOT_TOKEN, auth_date=int(time.time()) + 61)
    try:
        api.telegram_user_id_from_init_data(raw)
    except ValueError:
        pass
    else:
        raise AssertionError("future initData was accepted")


def test_api_case_query_contract(monkeypatch):
    from legal_bot import api
    monkeypatch.setattr(api, "BOT_TOKEN", "123456:TESTTOKEN")
    assert api.API_VERSION == "1"


def test_multi_document_analysis_api_is_case_scoped(monkeypatch):
    from legal_bot import api

    class FakeCaseService:
        def get(self, uid, cid):
            assert (uid, cid) == (12345, 77)
            return {'id': cid}

    class FakeDocumentService:
        def list(self, uid, cid):
            assert (uid, cid) == (12345, 77)
            return [{'id': 1, 'file_name': 'الف.txt', 'extracted_text': 'مبلغ ۱۰۰ ریال'},
                    {'id': 2, 'file_name': 'ب.txt', 'extracted_text': 'مبلغ ۲۰۰ ریال'}]

    monkeypatch.setattr(api, 'CaseService', FakeCaseService)
    monkeypatch.setattr(api, 'DocumentService', FakeDocumentService)
    handler = object.__new__(api.APIHandler)
    captured = {}
    handler._send = lambda status, payload, **kwargs: captured.update(status=status, payload=payload)
    handler._analyze_case_documents(12345, 77)
    assert captured['status'] == 200
    data = captured['payload']['data']
    assert data['case_id'] == 77
    assert data['documents_analyzed'] == 2
    assert data['comparison_candidate_count'] == 1


def test_miniapp_upload_endpoint_parses_multipart_file_parts(monkeypatch):
    from io import BytesIO
    from legal_bot import api

    boundary = "machina-test-boundary"
    payload = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="files"; filename="contract.txt"\r\n'
        "Content-Type: text/plain; charset=utf-8\r\n\r\n"
        "متن قرارداد برای آزمون آپلود\r\n"
        f"--{boundary}--\r\n"
    ).encode("utf-8")
    captured = {}

    class FakeDocumentService:
        def add_files(self, uid, cid, files):
            assert (uid, cid) == (12345, 77)
            assert len(files) == 1
            assert files[0]["name"] == "contract.txt"
            assert Path(files[0]["path"]).read_text(encoding="utf-8").strip() == "متن قرارداد برای آزمون آپلود"
            return {"documents": [{"document_id": 1}], "document_count": 1}

        def public_list(self, uid, cid):
            assert (uid, cid) == (12345, 77)
            return [{"id": 1, "file_name": "contract.txt"}]

    from pathlib import Path
    monkeypatch.setattr(api, "DocumentService", FakeDocumentService)
    handler = object.__new__(api.APIHandler)
    handler.headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(payload)),
    }
    handler.rfile = BytesIO(payload)
    handler._send = lambda status, data: captured.update(status=status, data=data)

    handler._upload_documents(12345, 77)
    assert captured["status"] == 201
    assert captured["data"]["data"]["documents"] == [{"id": 1, "file_name": "contract.txt"}]


def test_workflow_agent_api_returns_conflict_on_concurrent_checkpoint_change(monkeypatch, tmp_path):
    from legal_bot import api, db
    from legal_bot.core.cases import CaseService

    db_path = tmp_path / 'workflow-api-conflict.sqlite3'
    monkeypatch.setattr(db, 'DB_PATH', db_path)
    db.init_db(); db.v193_upgrade(); db.v20_upgrade(); db.v67_upgrade()
    db.init_case_workspace_tables(); db.init_case_workflow_agent_tables()
    db.register_user(12345, 'api-workflow-hash', '1234', full_name='Workflow API')
    case = CaseService().create_empty(12345, 'پرونده آزمون گردش کار')
    cid = case['id']

    handler = object.__new__(api.APIHandler)
    captured = {}
    handler._send = lambda status, payload, **kwargs: captured.update(status=status, payload=payload)
    handler._error = lambda status, code, message: captured.update(status=status, payload={'error': {'code': code, 'message': message}})

    handler._case_workflow_agent_action(12345, cid, 'start', {'query': 'قرارداد'})
    assert captured['status'] == 200
    handler._case_workflow_agent_action(12345, cid, 'approve', {'step': 'search', 'approved': True})
    assert captured['status'] == 200

    monkeypatch.setattr(db, 'save_case_workflow_agent_session_if_unchanged', lambda *a, **k: None)
    handler._case_workflow_agent_action(12345, cid, 'approve', {'step': 'search', 'approved': False})
    assert captured['status'] == 409
    assert captured['payload']['error']['code'] == 'workflow_state_conflict'


def test_workflow_agent_api_full_lifecycle_persists_each_step(monkeypatch, tmp_path):
    from legal_bot import api, db
    from legal_bot.core.cases import CaseService

    db_path = tmp_path / 'workflow-api-lifecycle.sqlite3'
    monkeypatch.setattr(db, 'DB_PATH', db_path)
    db.init_db(); db.v193_upgrade(); db.v20_upgrade(); db.v67_upgrade()
    db.init_case_workspace_tables(); db.init_case_workflow_agent_tables()
    db.register_user(12346, 'api-workflow-life', '1234', full_name='Workflow Lifecycle')
    cid = CaseService().create_empty(12346, 'پرونده چرخه کامل')['id']

    class FakeDocumentService:
        def list(self, uid, case_id):
            assert (uid, case_id) == (12346, cid)
            return [
                {'id': 11, 'file_name': 'قرارداد.txt', 'extracted_text': '[صفحه ۱]\nمبلغ قرارداد ۱۰۰ ریال'},
                {'id': 12, 'file_name': 'الحاقیه.txt', 'extracted_text': '[صفحه ۲]\nمبلغ قرارداد ۲۰۰ ریال'},
            ]

    monkeypatch.setattr(api, 'DocumentService', FakeDocumentService)
    handler = object.__new__(api.APIHandler)
    captured = {}
    handler._send = lambda status, payload, **kwargs: captured.update(status=status, payload=payload)
    handler._error = lambda status, code, message: captured.update(status=status, payload={'error': {'code': code, 'message': message}})

    handler._case_workflow_agent_action(12346, cid, 'start', {'query': 'مبلغ قرارداد'})
    assert captured['status'] == 200
    for step in ('search', 'extract_compare', 'lawyer_review', 'complete'):
        handler._case_workflow_agent_action(12346, cid, 'approve', {'step': step, 'approved': True})
        assert captured['status'] == 200
        handler._case_workflow_agent_action(12346, cid, 'run', {})
        assert captured['status'] == 200

    stored = db.get_case_workflow_agent_session(12346, cid)
    assert stored['state']['status'] == 'COMPLETED'
    assert stored['state']['completed_steps'] == ['search', 'extract_compare', 'lawyer_review', 'complete']
    assert stored['state']['results']['document_analysis']['documents_analyzed'] == 2
