import tempfile
from pathlib import Path


def _setup(monkeypatch, user_id=994001):
    td = tempfile.TemporaryDirectory()
    db_path = str(Path(td.name) / 'test.sqlite3')
    monkeypatch.setenv('DB_PATH', db_path)
    from legal_bot import db
    db.DB_PATH = db_path
    db.init_db()
    db.v193_upgrade(); db.v20_upgrade(); db.v67_upgrade()
    db.init_case_workspace_tables(); db.init_case_dates_table(); db.init_case_reminders_table()
    db.register_user(user_id, 'hash-draft', '9999', full_name='Draft User')
    return td, db


def _case(db, uid):
    with db.conn() as c:
        cur = c.execute(
            "INSERT INTO cases(user_id,file_name,status,result,created_at) VALUES(?,?,?,?,?)",
            (uid, 'test.pdf', 'ready', '', db.now_iso())
        )
        c.commit()
        return cur.lastrowid


def test_draft_artifact_is_durable_and_versioned(monkeypatch):
    td, db = _setup(monkeypatch)
    try:
        uid = 994001
        cid = _case(db, uid)
        from legal_bot.drafting_artifacts import save_draft_artifact, latest_draft_artifact, list_draft_artifacts
        a1 = save_draft_artifact(uid, cid, status='READY_FOR_REVIEW', draft_text='نسخه اول', gate={'status':'PASS'}, output={'draft_text':'نسخه اول'})
        a2 = save_draft_artifact(uid, cid, status='NEEDS_LAWYER_REVIEW', draft_text='نسخه دوم', gate={'status':'BLOCKED'}, output={'draft_text':'نسخه دوم'})
        assert a1['version_no'] == 1
        assert a2['version_no'] == 2
        assert latest_draft_artifact(uid, cid)['draft_text'] == 'نسخه دوم'
        assert len(list_draft_artifacts(uid, cid)) == 2
    finally:
        td.cleanup()


def test_draft_artifact_is_case_owned(monkeypatch):
    td, db = _setup(monkeypatch, 994002)
    try:
        uid = 994002
        cid = _case(db, uid)
        from legal_bot.drafting_artifacts import save_draft_artifact, latest_draft_artifact
        a = save_draft_artifact(uid, cid, status='READY_FOR_REVIEW', draft_text='متن')
        assert latest_draft_artifact(994999, cid) is None
        with db.conn() as c:
            assert c.execute('SELECT COUNT(*) n FROM drafting_artifacts WHERE id=?', (a['id'],)).fetchone()['n'] == 1
    finally:
        td.cleanup()


def test_draft_artifact_history_is_limited_and_case_scoped(monkeypatch):
    td, db = _setup(monkeypatch, 994003)
    try:
        uid = 994003
        cid1 = _case(db, uid)
        cid2 = _case(db, uid)
        from legal_bot.drafting_artifacts import save_draft_artifact, list_draft_artifacts, get_draft_artifact
        ids=[]
        for i in range(15):
            ids.append(save_draft_artifact(uid, cid1, status="READY_FOR_REVIEW", draft_text=f"v{i}")["id"])
        save_draft_artifact(uid, cid2, status="READY_FOR_REVIEW", draft_text="other")
        assert len(list_draft_artifacts(uid, cid1, limit=12)) == 12
        assert get_draft_artifact(uid, cid2, ids[0]) is None
    finally:
        td.cleanup()


def test_drafting_workflow_requires_information_before_artifact(monkeypatch):
    td, db = _setup(monkeypatch, 994004)
    try:
        uid = 994004
        cid = _case(db, uid)
        from legal_bot.drafting_workflow import run_drafting_workflow
        r = run_drafting_workflow(uid, cid, brief_type="لایحه دفاعیه")
        assert r["status"] == "NEEDS_INFORMATION"
        assert r["artifact"] is None
    finally:
        td.cleanup()


def test_drafting_workflow_rejects_archived_case(monkeypatch):
    td, db = _setup(monkeypatch, 994005)
    try:
        uid = 994005
        cid = _case(db, uid)
        with db.conn() as c:
            c.execute("UPDATE cases SET status='archived' WHERE id=? AND user_id=?", (cid, uid))
            c.commit()
        from legal_bot.drafting_workflow import run_drafting_workflow
        r = run_drafting_workflow(uid, cid, brief_type="لایحه دفاعیه")
        assert r["status"] == "CASE_ARCHIVED"
        assert r["artifact"] is None
    finally:
        td.cleanup()


def test_draft_artifact_rejects_archived_case(monkeypatch):
    td, db = _setup(monkeypatch, 994006)
    try:
        uid = 994006
        cid = _case(db, uid)
        with db.conn() as c:
            c.execute("UPDATE cases SET status='archived' WHERE id=? AND user_id=?", (cid, uid))
            c.commit()
        from legal_bot.drafting_artifacts import save_draft_artifact
        import pytest
        with pytest.raises(ValueError, match="case_archived"):
            save_draft_artifact(uid, cid, status="READY_FOR_REVIEW", draft_text="متن")
    finally:
        td.cleanup()
