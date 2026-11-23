from datetime import datetime, timezone
from pathlib import Path

import pytest

from legal_bot import db
from legal_bot.lawyer_library import (
    create_lawyer_library_item,
    delete_lawyer_library_item,
    list_lawyer_library,
    update_lawyer_library_item,
)


def _seed(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "lawyer-library.sqlite3")
    db.init_db()
    now = datetime.now(timezone.utc).isoformat()
    with db.conn() as c:
        for uid in (701, 702):
            c.execute(
                "INSERT INTO users(user_id,free_month,created_at) VALUES(?,?,?)",
                (uid, "2026-10", now),
            )
        c.commit()


def test_starter_library_has_prompts_and_templates_and_searches(monkeypatch, tmp_path):
    _seed(monkeypatch, tmp_path)
    all_items = list_lawyer_library(701)
    assert len(all_items) >= 6
    assert {item["kind"] for item in all_items} == {"prompt", "template"}
    assert list_lawyer_library(701, kind="template")
    assert any("خلأهای اثباتی" in item["title"] for item in list_lawyer_library(701, query="اثباتی"))


def test_personal_library_items_are_private_and_deletable(monkeypatch, tmp_path):
    _seed(monkeypatch, tmp_path)
    item = create_lawyer_library_item(701, {
        "kind": "prompt", "title": "دستور اختصاصی", "category": "تحلیل",
        "description": "تست", "content": "فقط بر اساس متن پرونده تحلیل کن.",
    })
    own = list_lawyer_library(701)
    other = list_lawyer_library(702)
    assert any(x["id"] == item["id"] for x in own)
    assert all(x["id"] != item["id"] for x in other)
    assert delete_lawyer_library_item(702, item["id"]) is False
    updated = update_lawyer_library_item(701, item["id"], {
        "kind": "template", "title": "قالب ویرایش‌شده", "category": "نگارش",
        "description": "توضیح جدید", "content": "ساختار سند را با جای‌خالی‌ها تهیه کن.",
    })
    assert updated["title"] == "قالب ویرایش‌شده"
    assert updated["kind"] == "template"
    assert update_lawyer_library_item(702, item["id"], {"title": "غیرمجاز", "content": "x"}) is None
    assert delete_lawyer_library_item(701, item["id"]) is True
    assert all(x["id"] != item["id"] for x in list_lawyer_library(701))


def test_library_validates_lengths_and_kinds(monkeypatch, tmp_path):
    _seed(monkeypatch, tmp_path)
    with pytest.raises(ValueError):
        create_lawyer_library_item(701, {"kind": "playbook", "title": "x", "content": "y"})
    with pytest.raises(ValueError):
        create_lawyer_library_item(701, {"kind": "prompt", "title": "x", "content": ""})
    with pytest.raises(ValueError):
        create_lawyer_library_item(701, {"kind": "prompt", "title": "x" * 101, "content": "متن"})


def test_library_api_and_existing_work_shelf_are_integrated(monkeypatch, tmp_path):
    _seed(monkeypatch, tmp_path)
    from legal_bot import api
    handler = object.__new__(api.APIHandler)
    handler.path = "/api/v1/lawyer-library?kind=prompt"
    captured = {}
    handler._send = lambda status, payload, **kwargs: captured.update(status=status, payload=payload)
    handler._lawyer_library(701)
    assert captured["status"] == 200
    assert captured["payload"]["data"]["count"] >= 4

    root = Path(__file__).resolve().parents[1]
    app = (root / "miniapp" / "app.js").read_text(encoding="utf-8")
    html = (root / "miniapp" / "index.html").read_text(encoding="utf-8")
    assert "/api/v1/lawyer-library" in app
    assert "openLibraryCreateModal" in app
    assert "applyLibraryResource" in app
    assert 'id="workTabLibrary"' in html
    assert 'id="lawyerLibraryList"' in html
