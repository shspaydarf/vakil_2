import tempfile
from pathlib import Path

import pytest


def _setup(monkeypatch, uid=995001):
    td = tempfile.TemporaryDirectory()
    db_path = str(Path(td.name) / "review.sqlite3")
    monkeypatch.setenv("DB_PATH", db_path)
    from legal_bot import db
    db.DB_PATH = db_path
    db.init_db()
    db.v193_upgrade(); db.v20_upgrade(); db.v67_upgrade()
    db.init_case_workspace_tables(); db.init_case_dates_table(); db.init_case_reminders_table()
    db.register_user(uid, "review-hash", "1111", full_name="Review User")
    with db.conn() as c:
        cur = c.execute(
            "INSERT INTO cases(user_id,file_name,status,result,created_at) VALUES(?,?,?,?,?)",
            (uid, "draft.pdf", "ready", "", db.now_iso()),
        )
        c.commit()
        cid = cur.lastrowid
    return td, db, uid, cid


def test_review_events_are_append_only_and_case_scoped(monkeypatch):
    td, db, uid, cid = _setup(monkeypatch)
    try:
        from legal_bot.drafting_artifacts import save_draft_artifact, record_draft_review, list_draft_reviews, get_draft_artifact
        artifact = save_draft_artifact(uid, cid, status="NEEDS_LAWYER_REVIEW", draft_text="پیش‌نویس اولیه")
        e1 = record_draft_review(uid, cid, artifact["id"], decision="changes_requested", note="بند ۲ بررسی شود", confirm_review=True)
        e2 = record_draft_review(uid, cid, artifact["id"], decision="reviewed_ok", note="بازبینی انجام شد", confirm_review=True)
        assert e1["id"] < e2["id"]
        events = list_draft_reviews(uid, cid, artifact["id"])
        assert [e["decision"] for e in events] == ["reviewed_ok", "changes_requested"]
        assert get_draft_artifact(uid, cid, artifact["id"])["draft_text"] == "پیش‌نویس اولیه"
        assert list_draft_reviews(uid + 100, cid, artifact["id"]) == []
    finally:
        td.cleanup()


def test_review_requires_explicit_confirmation_and_bounded_note(monkeypatch):
    td, db, uid, cid = _setup(monkeypatch, 995002)
    try:
        from legal_bot.drafting_artifacts import save_draft_artifact, record_draft_review
        artifact = save_draft_artifact(uid, cid, status="READY_FOR_REVIEW", draft_text="متن")
        with pytest.raises(ValueError, match="review_confirmation_required"):
            record_draft_review(uid, cid, artifact["id"], decision="reviewed_ok", confirm_review=False)
        with pytest.raises(ValueError, match="review_note_too_long"):
            record_draft_review(uid, cid, artifact["id"], decision="reviewed_ok", note="x" * 8001, confirm_review=True)
        with pytest.raises(ValueError, match="review_decision_invalid"):
            record_draft_review(uid, cid, artifact["id"], decision="approved_without_review", confirm_review=True)
    finally:
        td.cleanup()


def test_archived_case_cannot_accept_review_event(monkeypatch):
    td, db, uid, cid = _setup(monkeypatch, 995003)
    try:
        from legal_bot.drafting_artifacts import save_draft_artifact, record_draft_review, list_draft_reviews
        artifact = save_draft_artifact(uid, cid, status="READY_FOR_REVIEW", draft_text="متن")
        with db.conn() as c:
            c.execute("UPDATE cases SET status='archived' WHERE id=? AND user_id=?", (cid, uid))
            c.commit()
        with pytest.raises(ValueError, match="case_archived"):
            record_draft_review(uid, cid, artifact["id"], decision="reviewed_ok", confirm_review=True)
        assert list_draft_reviews(uid, cid, artifact["id"]) == []
    finally:
        td.cleanup()


def test_review_api_routes_are_registered():
    from legal_bot.api import APIHandler
    import inspect
    get_source = inspect.getsource(APIHandler.do_GET)
    post_source = inspect.getsource(APIHandler.do_POST)
    assert "/drafts/([^/]+)/reviews" in get_source
    assert "/drafts/([^/]+)/review" in post_source
