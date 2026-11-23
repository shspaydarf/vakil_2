import tempfile
from pathlib import Path

from legal_bot import db
from legal_bot.core.cases import CaseService


def setup_module(module):
    module._old_db = db.DB_PATH
    module._tmp = tempfile.TemporaryDirectory()
    db.DB_PATH = Path(module._tmp.name) / "recent-activity.db"
    db.init_db()
    db.v193_upgrade(); db.v20_upgrade(); db.v67_upgrade()
    db.register_user(1101, "recent-a", "1101", full_name="A")
    db.register_user(2202, "recent-b", "2202", full_name="B")
    db.init_case_workspace_tables()
    module.case_a = CaseService().create_empty(1101, "پرونده وکیل الف")
    module.case_b = CaseService().create_empty(2202, "پرونده وکیل ب")
    db.init_case_workspace_tables()


def teardown_module(module):
    db.DB_PATH = module._old_db
    module._tmp.cleanup()


def test_recent_activity_is_private_to_each_lawyer():
    assert db.record_recent_activity(1101, case_a["id"], "case_opened") is True
    assert db.list_recent_activity(1101)[0]["case_name"] == "پرونده وکیل الف"
    assert db.list_recent_activity(2202) == []
    assert db.record_recent_activity(2202, case_a["id"], "case_opened") is False


def test_recent_activity_accepts_only_known_types_and_owned_active_cases():
    before = db.list_recent_activity(1101)
    assert db.record_recent_activity(1101, case_a["id"], "client_private_note") is False
    assert db.record_recent_activity(1101, case_b["id"], "case_opened") is False
    assert db.list_recent_activity(1101) == before


def test_recent_activity_is_bounded_and_newest_first():
    for _ in range(65):
        assert db.record_recent_activity(1101, case_a["id"], "documents_opened") is True
    items = db.list_recent_activity(1101, limit=30)
    assert len(items) == 20  # API/database hard cap
    with db.conn() as c:
        count = c.execute("SELECT COUNT(*) FROM lawyer_recent_activity WHERE user_id=?", (1101,)).fetchone()[0]
    assert count == 60


def test_recent_activity_api_methods(monkeypatch):
    from legal_bot import api
    handler = object.__new__(api.APIHandler)
    captured = {}
    handler.path = "/api/v1/recent-activity?limit=3"
    handler._send = lambda status, payload, **kwargs: captured.update(status=status, payload=payload)
    handler._recent_activity(1101)
    assert captured["status"] == 200
    assert len(captured["payload"]["data"]["items"]) <= 3

    handler._record_recent_activity(1101, {"case_id": case_a["id"], "activity_type": "timeline_opened"})
    assert captured["status"] == 201
    assert captured["payload"]["data"]["recorded"] is True
    handler._record_recent_activity(2202, {"case_id": case_a["id"], "activity_type": "case_opened"})
    assert captured["status"] == 404


def test_miniapp_has_recent_activity_panel_and_safe_tracking():
    root = Path(__file__).resolve().parents[1]
    app = (root / "miniapp" / "app.js").read_text(encoding="utf-8")
    html = (root / "miniapp" / "index.html").read_text(encoding="utf-8")
    assert "async function loadRecentActivity()" in app
    assert "recordRecentActivity('documents_opened')" in app
    assert "recordRecentActivity('draft_created')" in app
    assert "/api/v1/recent-activity" in app
    assert 'id="recentActivityList"' in html
    assert html.count('id="pinnedCasesBtn"') == 1
