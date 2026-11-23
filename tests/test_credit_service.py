import tempfile
from pathlib import Path


def test_credit_service_reserve_commit_refund(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.sqlite3"
        monkeypatch.setenv("DB_PATH", str(db_path))
        from legal_bot import db
        from legal_bot.core.credits import CreditService
        db.DB_PATH = db_path

        db.init_db()
        db.v193_upgrade(); db.v20_upgrade(); db.v67_upgrade()
        db.init_case_workspace_tables(); db.init_case_dates_table(); db.init_case_reminders_table()
        db.register_user(991001, "hash-a", "1234", full_name="A")
        service = CreditService()

        status = service.status(991001)
        assert status["remaining"] > 0
        before = status["remaining"]

        ok, ref = service.reserve_case(991001)
        assert ok and ref
        assert service.status(991001)["remaining"] == before - 10
        assert service.commit(991001, ref)
        assert not service.refund_case(991001, ref)

        ok, ref = service.reserve_case(991001)
        assert ok
        assert service.refund_case(991001, ref)
        assert service.status(991001)["remaining"] == before - 10
