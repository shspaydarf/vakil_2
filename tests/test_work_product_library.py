from datetime import datetime, timezone
from pathlib import Path

from legal_bot import db
from legal_bot.drafting_artifacts import save_draft_artifact, list_work_products, set_work_product_saved


def _seed(monkeypatch, tmp_path):
    monkeypatch.setattr(db, 'DB_PATH', tmp_path / 'work-products.sqlite3')
    db.init_db()
    now = datetime.now(timezone.utc).isoformat()
    with db.conn() as c:
        for uid in (401, 402):
            c.execute('INSERT INTO users(user_id,free_month,created_at) VALUES(?,?,?)', (uid, '2026-10', now))
        c.execute('INSERT INTO cases(user_id,file_name,status,created_at) VALUES(?,?,?,?)', (401, 'پرونده وکیل اول', 'completed', now))
        c.execute('INSERT INTO cases(user_id,file_name,status,created_at) VALUES(?,?,?,?)', (402, 'پرونده وکیل دوم', 'completed', now))
        c.commit()
    db.add_case_ai_exchange(401, 1, 'ریسک‌های قرارداد چیست؟', 'پاسخ محرمانه هوش مصنوعی', 'full')
    draft = save_draft_artifact(401, 1, status='READY_FOR_REVIEW', draft_text='متن پیش‌نویس محرمانه', brief_type='لایحه دفاعیه')
    return draft


def test_work_product_library_lists_ai_and_drafts_and_is_private(monkeypatch, tmp_path):
    draft = _seed(monkeypatch, tmp_path)
    items = list_work_products(401)
    assert {x['item_type'] for x in items} == {'ai', 'draft'}
    assert all('body' not in x for x in items)
    assert list_work_products(402) == []
    assert len(list_work_products(401, query='قرارداد')) == 1
    assert set_work_product_saved(401, 'draft', draft['id'], True)
    assert len(list_work_products(401, saved_only=True)) == 1
    assert list_work_products(402, saved_only=True) == []


def test_work_product_bookmark_rejects_other_lawyer_and_unknown_items(monkeypatch, tmp_path):
    draft = _seed(monkeypatch, tmp_path)
    assert set_work_product_saved(402, 'draft', draft['id'], True) is False
    assert set_work_product_saved(401, 'unknown', '1', True) is False
    assert set_work_product_saved(401, 'draft', draft['id'], True)
    assert set_work_product_saved(401, 'draft', draft['id'], False)
    assert list_work_products(401, saved_only=True) == []


def test_work_product_api_and_miniapp_integration(monkeypatch, tmp_path):
    _seed(monkeypatch, tmp_path)
    from legal_bot import api
    handler = object.__new__(api.APIHandler)
    handler.path = '/api/v1/work-products?limit=20'
    captured = {}
    handler._send = lambda status, payload, **kwargs: captured.update(status=status, payload=payload)
    handler._work_products(401)
    assert captured['status'] == 200
    assert captured['payload']['data']['count'] == 2
    root = Path(__file__).resolve().parents[1]
    app = (root / 'miniapp' / 'app.js').read_text(encoding='utf-8')
    html = (root / 'miniapp' / 'index.html').read_text(encoding='utf-8')
    assert '/api/v1/work-products' in app
    assert 'openWorkProduct' in app
    assert 'id="workProductsList"' in html
