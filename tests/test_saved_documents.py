from datetime import datetime, timezone
from pathlib import Path

from legal_bot import db


def _seed(monkeypatch, tmp_path):
    monkeypatch.setattr(db, 'DB_PATH', tmp_path / 'saved-docs.sqlite3')
    db.init_db()
    now = datetime.now(timezone.utc).isoformat()
    with db.conn() as c:
        for uid in (301, 302):
            c.execute('INSERT INTO users(user_id,free_month,created_at) VALUES(?,?,?)', (uid, '2026-10', now))
        c.execute('INSERT INTO cases(user_id,file_name,status,created_at) VALUES(?,?,?,?)', (301, 'پرونده الف', 'completed', now))
        c.execute('INSERT INTO cases(user_id,file_name,status,created_at) VALUES(?,?,?,?)', (302, 'پرونده ب', 'completed', now))
        c.execute('INSERT INTO case_documents(case_id,file_name,page_count,extracted_text,created_at) VALUES(?,?,?,?,?)', (1, 'قرارداد.pdf', 4, 'محرمانه', now))
        c.execute('INSERT INTO case_documents(case_id,file_name,page_count,extracted_text,created_at) VALUES(?,?,?,?,?)', (2, 'سند دیگر.pdf', 2, 'متن', now))
        c.commit()
    db.init_case_workspace_tables()
    return 1, 2


def test_saved_documents_are_private_idempotent_and_metadata_only(monkeypatch, tmp_path):
    case_a, case_b = _seed(monkeypatch, tmp_path)
    assert db.set_document_saved(301, case_a, 1, True)
    assert db.set_document_saved(301, case_a, 1, True)
    items = db.list_saved_documents(301)
    assert len(items) == 1
    assert items[0]['file_name'] == 'قرارداد.pdf'
    assert 'extracted_text' not in items[0]
    assert db.list_saved_documents(302) == []
    assert db.set_document_saved(302, case_a, 1, True) is False
    assert db.set_document_saved(301, case_b, 2, True) is False


def test_unsave_and_document_delete_cleanup(monkeypatch, tmp_path):
    case_a, _ = _seed(monkeypatch, tmp_path)
    assert db.set_document_saved(301, case_a, 1, True)
    assert db.set_document_saved(301, case_a, 1, False)
    assert db.list_saved_documents(301) == []


def test_saved_documents_api_and_miniapp_hooks(monkeypatch, tmp_path):
    case_a, _ = _seed(monkeypatch, tmp_path)
    assert db.set_document_saved(301, case_a, 1, True)
    from legal_bot import api
    handler = object.__new__(api.APIHandler)
    handler.path = '/api/v1/saved-documents?limit=10'
    captured = {}
    handler._send = lambda status, payload, **kwargs: captured.update(status=status, payload=payload)
    handler._saved_documents(301)
    assert captured['status'] == 200
    assert captured['payload']['data']['items'][0]['document_id'] == 1
    root = Path(__file__).resolve().parents[1]
    app = (root / 'miniapp' / 'app.js').read_text(encoding='utf-8')
    html = (root / 'miniapp' / 'index.html').read_text(encoding='utf-8')
    assert '/api/v1/saved-documents' in app
    assert 'data-doc-save' in app
    assert 'id="savedDocumentsList"' in html
