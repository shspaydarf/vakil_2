import tempfile
from pathlib import Path


def _setup(monkeypatch, user_id=992001):
    td = tempfile.TemporaryDirectory()
    monkeypatch.setenv("DB_PATH", str(Path(td.name) / "test.sqlite3"))
    from legal_bot import db
    db.DB_PATH = str(Path(td.name) / "test.sqlite3")
    db.init_db()
    db.v193_upgrade(); db.v20_upgrade(); db.v67_upgrade()
    db.init_case_workspace_tables(); db.init_case_dates_table(); db.init_case_reminders_table()
    db.register_user(user_id, "hash-ent", "9999", full_name="Entitlement User")
    return td, db


def test_free_case_uses_credit_reservation(monkeypatch):
    td, db = _setup(monkeypatch)
    try:
        from legal_bot.core.entitlements import EntitlementService
        from legal_bot.config import CREDIT_CASE_COST
        service = EntitlementService()
        before = service.status(992001)["credits"]["remaining"]
        ok, ref = service.reserve(992001, "case")
        assert ok and ref
        assert service.status(992001)["credits"]["remaining"] == before - CREDIT_CASE_COST
        assert service.commit(992001, ref)
        with db.conn() as conn:
            ledger = conn.execute(
                "SELECT status FROM credit_ledger WHERE user_id=? AND reference_id=?",
                (992001, ref),
            ).fetchone()
            reservation = conn.execute(
                "SELECT status FROM entitlement_reservations WHERE user_id=? AND reference_id=?",
                (992001, ref),
            ).fetchone()
        assert ledger["status"] == "committed"
        assert reservation["status"] == "committed"
        assert not service.refund(992001, ref)
    finally:
        td.cleanup()


def test_free_ai_uses_same_contract(monkeypatch):
    td, db = _setup(monkeypatch, 992002)
    try:
        from legal_bot.core.entitlements import EntitlementService
        from legal_bot.config import CREDIT_AI_QUESTION_COST
        service = EntitlementService()
        before = service.status(992002)["credits"]["remaining"]
        ok, ref = service.reserve(992002, "ai_question")
        assert ok and ref
        assert service.status(992002)["credits"]["remaining"] == before - CREDIT_AI_QUESTION_COST
        assert service.refund(992002, ref)
        assert service.status(992002)["credits"]["remaining"] == before
    finally:
        td.cleanup()


def test_paid_case_and_ai_share_unified_reservation_lifecycle(monkeypatch):
    td, db = _setup(monkeypatch, 992003)
    try:
        db.admin_grant(992003, days=30, limit=4)
        from legal_bot.core.entitlements import EntitlementService
        service = EntitlementService()
        status = service.status(992003)
        assert status["source"] == "subscription"
        assert status["case"]["remaining"] == 4

        ok, case_ref = service.reserve(992003, "case")
        assert ok and case_ref
        assert service.status(992003)["case"]["remaining"] == 3
        assert service.refund(992003, case_ref)
        assert service.status(992003)["case"]["remaining"] == 4

        ok, ai_ref = service.reserve(992003, "ai_question")
        assert ok and ai_ref
        assert service.status(992003)["ai_question"]["remaining"] == 99
        assert service.commit(992003, ai_ref)
        assert not service.refund(992003, ai_ref)
    finally:
        td.cleanup()


def test_blocked_user_cannot_reserve(monkeypatch):
    td, db = _setup(monkeypatch, 992004)
    try:
        with db.conn() as conn:
            conn.execute("UPDATE users SET blocked=1 WHERE user_id=?", (992004,))
            conn.commit()
        from legal_bot.core.entitlements import EntitlementService
        ok, reason = EntitlementService().reserve(992004, "case")
        assert not ok
        assert "مسدود" in reason
    finally:
        td.cleanup()


def test_paid_ai_migrates_existing_legacy_usage_once(monkeypatch):
    td, db = _setup(monkeypatch, 992005)
    try:
        db.admin_grant(992005, days=30, limit=4)
        from legal_bot.core.entitlements import EntitlementService
        from legal_bot.core.entitlements import EntitlementRepository
        period = EntitlementRepository._period_key()
        with db.conn() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS ai_question_quota(
                user_id INTEGER NOT NULL, period_key TEXT NOT NULL, used_questions INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(user_id, period_key))""")
            conn.execute("INSERT INTO ai_question_quota(user_id,period_key,used_questions) VALUES(?,?,?)", (992005, period, 7))
            conn.commit()
        service = EntitlementService()
        assert service.status(992005)["ai_question"]["used"] == 7
        ok, ref = service.reserve(992005, "ai_question")
        assert ok and ref
        assert service.status(992005)["ai_question"]["used"] == 8
    finally:
        td.cleanup()
