from datetime import datetime, timezone

from legal_bot import db


def _seed_user_and_case(monkeypatch, tmp_path):
    db_path = tmp_path / 'pins.sqlite3'
    monkeypatch.setattr(db, 'DB_PATH', db_path)
    db.init_db()
    now = datetime.now(timezone.utc).isoformat()
    with db.conn() as c:
        c.execute("INSERT INTO users(user_id, free_month, created_at) VALUES(?,?,?)", (101, '2026-10', now))
        c.execute("INSERT INTO users(user_id, free_month, created_at) VALUES(?,?,?)", (202, '2026-10', now))
        c.execute("INSERT INTO cases(user_id,file_name,status,created_at) VALUES(?,?,?,?)", (101, 'پرونده الف', 'completed', now))
        c.execute("INSERT INTO cases(user_id,file_name,status,created_at) VALUES(?,?,?,?)", (202, 'پرونده ب', 'completed', now))
        c.commit()
    return 1, 2


def test_case_pin_is_per_user_and_idempotent(monkeypatch, tmp_path):
    case_a, case_b = _seed_user_and_case(monkeypatch, tmp_path)
    assert db.set_case_pinned(101, case_a, True)
    assert db.set_case_pinned(101, case_a, True)
    assert db.list_pinned_case_ids(101) == [case_a]
    assert db.list_pinned_case_ids(202) == []
    assert db.set_case_pinned(101, case_a, False)
    assert db.list_pinned_case_ids(101) == []


def test_cannot_pin_another_lawyers_case(monkeypatch, tmp_path):
    case_a, case_b = _seed_user_and_case(monkeypatch, tmp_path)
    assert db.set_case_pinned(101, case_b, True) is False
    assert db.list_pinned_case_ids(101) == []
