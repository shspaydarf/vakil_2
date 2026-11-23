from datetime import datetime, timezone

from legal_bot import db
from legal_bot.api import APIHandler


def _seed(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "service-listings.sqlite3")
    db.init_db()
    now = datetime.now(timezone.utc).isoformat()
    with db.conn() as c:
        for uid in (801, 802):
            c.execute("INSERT INTO users(user_id,free_month,created_at) VALUES(?,?,?)", (uid, "2026-10", now))
        c.commit()


def test_service_listing_data_is_private_and_owner_can_soft_delete(monkeypatch, tmp_path):
    _seed(monkeypatch, tmp_path)
    lid = db.create_service_listing(801, "وکیل نمونه", "09120000000", "تهران", "حقوقی", "مشاوره", "fixed", "2000000")
    assert any(x["id"] == lid for x in db.list_service_listings(801))
    assert not db.list_service_listings(802)
    assert db.delete_service_listing(802, lid) is False
    assert db.get_service_listing(lid)["status"] == "pending"
    assert db.delete_service_listing(801, lid) is True
    assert not db.list_service_listings(801)


def test_service_form_validation_and_field_limits():
    handler = object.__new__(APIHandler)
    valid = {
        "full_name": "وکیل نمونه", "phone": "09120000000", "city": "تهران",
        "specialty": "حقوقی", "service_title": "مشاوره", "fee_type": "percent",
        "fee_value": "توافقی", "description": "توضیح", "charitable": "on",
    }
    normalized = handler._service_fields(valid)
    assert normalized["charitable"] is True
    assert normalized["fee_value"] == "توافقی"
    invalid = dict(valid, service_title="")
    try:
        handler._service_fields(invalid)
    except ValueError:
        pass
    else:
        raise AssertionError("empty service title must be rejected")
    invalid = dict(valid, description="x" * 2001)
    try:
        handler._service_fields(invalid)
    except ValueError:
        pass
    else:
        raise AssertionError("oversized description must be rejected")


def test_service_update_rejects_foreign_owner_before_upload(monkeypatch):
    handler = object.__new__(APIHandler)
    monkeypatch.setattr(db, "get_service_listing", lambda lid: {"id": lid, "user_id": 801, "status": "pending"})
    monkeypatch.setattr(handler, "_read_service_multipart", lambda: (_ for _ in ()).throw(AssertionError("must not read/upload foreign profile")))
    captured = {}
    monkeypatch.setattr(handler, "_send", lambda status, payload: captured.update(status=status, payload=payload))
    handler._update_service_listing(802, 55)
    assert captured["status"] == 404
    assert captured["payload"]["error"]["code"] == "service_not_found"


def test_saved_service_with_failed_admin_notification_returns_non_retry_status(monkeypatch, tmp_path):
    _seed(monkeypatch, tmp_path)
    handler = object.__new__(APIHandler)
    import sys, types
    fake_handlers = types.ModuleType("legal_bot.handlers")
    fake_handlers._validate_service_fields = lambda *args: (True, "")
    monkeypatch.setitem(sys.modules, "legal_bot.handlers", fake_handlers)
    monkeypatch.setattr(handler, "_read_service_multipart", lambda: ({
        "full_name": "وکیل نمونه", "phone": "09120000000", "city": "تهران",
        "specialty": "حقوقی", "service_title": "مشاوره", "fee_type": "fixed",
        "fee_value": "2000000", "description": "", "charitable": "",
    }, "license.jpg", "image/jpeg", b"image-bytes"))
    monkeypatch.setattr(handler, "_upload_service_license", lambda *args: ("telegram-file-id", 77, 9001))
    monkeypatch.setattr(handler, "_notify_service_admins", lambda *args: False)
    captured = {}
    monkeypatch.setattr(handler, "_send", lambda status, payload: captured.update(status=status, payload=payload))
    handler._create_service_listing(801)
    assert captured["status"] == 202
    assert captured["payload"]["data"]["notification_sent"] is False
    assert "دوباره ارسال نکنید" in captured["payload"]["data"]["notice"]
    assert len(db.list_service_listings(801)) == 1
