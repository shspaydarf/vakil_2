import tempfile
from pathlib import Path


def _setup(monkeypatch, user_id=991002):
    td = tempfile.TemporaryDirectory()
    db_path = Path(td.name) / "test.sqlite3"
    monkeypatch.setenv("DB_PATH", str(db_path))
    from legal_bot import config, db
    monkeypatch.setattr(config, "DB_PATH", str(db_path))
    monkeypatch.setattr(db, "DB_PATH", db_path)
    db.init_db()
    db.v193_upgrade(); db.v20_upgrade(); db.v67_upgrade()
    db.init_case_workspace_tables(); db.init_case_dates_table(); db.init_case_reminders_table()
    db.register_user(user_id, "hash-ai", "5678", full_name="AI User")
    return td, db


def test_ai_free_user_reserve_commit_refund(monkeypatch):
    td, db = _setup(monkeypatch)
    try:
        from legal_bot.core.ai_entitlement import AIEntitlementService
        service = AIEntitlementService()
        before = service.status(991002)
        assert before is not None
        ok, ref = service.reserve_question(991002)
        assert ok and ref
        after = service.status(991002)
        assert after["remaining"] == before["remaining"] - service.repo.question_cost
        assert service.commit(991002, ref)
        assert not service.refund(991002, ref)

        ok, ref = service.reserve_question(991002)
        assert ok
        assert service.refund(991002, ref)
        assert service.status(991002)["remaining"] == after["remaining"]
    finally:
        td.cleanup()
