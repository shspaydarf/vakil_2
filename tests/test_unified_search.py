import sqlite3
from pathlib import Path

import pytest

from legal_bot import db
from legal_bot.unified_search import search_user_workspace


@pytest.fixture
def search_db(tmp_path, monkeypatch):
    path = tmp_path / "search.sqlite3"
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
      CREATE TABLE cases(id INTEGER PRIMARY KEY,user_id INTEGER,file_name TEXT,status TEXT,result TEXT,created_at TEXT,updated_at TEXT);
      CREATE TABLE case_documents(id INTEGER PRIMARY KEY,case_id INTEGER,file_name TEXT,extracted_text TEXT,created_at TEXT);
      CREATE TABLE case_versions(id INTEGER PRIMARY KEY,case_id INTEGER,file_name TEXT,extracted_text TEXT,created_at TEXT);
      CREATE TABLE case_lawyer_notes(case_id INTEGER PRIMARY KEY,user_id INTEGER,note_text TEXT,updated_at TEXT);
      CREATE TABLE case_tasks(id INTEGER PRIMARY KEY,user_id INTEGER,case_id INTEGER,title TEXT,due_at TEXT,created_at TEXT);
      CREATE TABLE case_events(id INTEGER PRIMARY KEY,user_id INTEGER,case_id INTEGER,title TEXT,details TEXT,created_at TEXT);
      CREATE TABLE case_ai_history(id INTEGER PRIMARY KEY,user_id INTEGER,case_id INTEGER,question TEXT,answer TEXT,created_at TEXT);
      CREATE TABLE drafting_artifacts(id TEXT PRIMARY KEY,user_id INTEGER,case_id INTEGER,brief_type TEXT,draft_text TEXT,version_no INTEGER,created_at TEXT,updated_at TEXT);
      CREATE TABLE clients(id INTEGER PRIMARY KEY,user_id INTEGER,name TEXT,phone TEXT,national_id TEXT,note TEXT,updated_at TEXT);
      CREATE TABLE lawyer_library_items(id TEXT PRIMARY KEY,user_id INTEGER,title TEXT,category TEXT,description TEXT,content TEXT,updated_at TEXT);
    """)
    conn.executemany("INSERT INTO cases VALUES(?,?,?,?,?,?,?)", [
        (1, 77, "پرونده قرارداد الف", "completed", "", "2026-01-01", "2026-01-02"),
        (2, 88, "پرونده محرمانه ب", "completed", "", "2026-01-01", "2026-01-02"),
        (3, 77, "پرونده بایگانی", "archived", "", "2026-01-01", "2026-01-02"),
    ])
    conn.execute("INSERT INTO case_documents VALUES(?,?,?,?,?)", (10,1,"قرارداد.pdf","[صفحه 2]\nموعد تحویل ملک در خرداد ماه تعیین شده است.","2026-01-02"))
    conn.execute("INSERT INTO case_documents VALUES(?,?,?,?,?)", (11,2,"سند محرمانه.pdf","موعد تحویل ملک در خرداد ماه بوده است.","2026-01-02"))
    conn.execute("INSERT INTO case_lawyer_notes VALUES(?,?,?,?)", (1,77,"پیگیری تحویل ملک در خرداد","2026-01-03"))
    conn.execute("INSERT INTO case_tasks VALUES(?,?,?,?,?,?)", (1,77,1,"پیگیری تحویل ملک","2026-06-01","2026-01-03"))
    conn.execute("INSERT INTO case_ai_history VALUES(?,?,?,?,?,?)", (1,77,1,"موعد تحویل چه زمانی است؟","در متن قرارداد خرداد ذکر شده است.","2026-01-04"))
    conn.execute("INSERT INTO drafting_artifacts VALUES(?,?,?,?,?,?,?,?)", ("d1",77,1,"لایحه","درخواست الزام به تحویل ملک در خرداد",1,"2026-01-04","2026-01-04"))
    conn.execute("INSERT INTO clients VALUES(?,?,?,?,?,?,?)", (1,77,"علی رضایی","09120000000","0012345678","موکل پرونده تحویل ملک","2026-01-04"))
    conn.execute("INSERT INTO lawyer_library_items VALUES(?,?,?,?,?,?,?)", ("l1",77,"قالب تحویل ملک","قالب","شرح","متن نمونه تحویل ملک","2026-01-04"))
    conn.commit(); conn.close()

    def connect():
        c = sqlite3.connect(path)
        c.row_factory = sqlite3.Row
        return c
    monkeypatch.setattr(db, "conn", connect)
    return path


def test_unified_search_finds_multiple_private_sources_and_provenance(search_db):
    data = search_user_workspace(77, "تحویل ملک خرداد", scopes=("documents", "notes", "tasks", "ai", "drafts", "clients", "library"), limit=40)
    kinds = {x["kind"] for x in data["items"]}
    assert {"documents", "notes", "tasks", "ai", "drafts", "clients", "library"}.issubset(kinds)
    doc = next(x for x in data["items"] if x["kind"] == "documents")
    assert doc["case_id"] == 1
    assert doc["case_name"] == "پرونده قرارداد الف"
    assert doc["page"] == 2
    assert data["privacy_note"]


def test_unified_search_never_returns_other_users_or_archived_cases(search_db):
    data = search_user_workspace(77, "موعد تحویل ملک خرداد", scopes=("documents", "cases"), limit=50)
    assert all(x.get("case_id") != 2 for x in data["items"])
    assert all(x.get("case_id") != 3 for x in data["items"])
    assert not any("محرمانه" in x["title"] for x in data["items"])


def test_unified_search_rejects_bad_query_and_scope(search_db):
    with pytest.raises(ValueError):
        search_user_workspace(77, "x")
    with pytest.raises(ValueError):
        search_user_workspace(77, "قرارداد", scopes=("all_users",))


def test_unified_search_does_not_expose_client_phone_or_national_id(search_db):
    data = search_user_workspace(77, "علی رضایی", scopes=("clients",))
    assert data["count"] == 1
    serialized = str(data["items"])
    assert "09120000000" not in serialized
    assert "0012345678" not in serialized


def test_api_unified_search_uses_authenticated_uid_and_validates_scope(monkeypatch):
    from legal_bot import api
    calls = {}
    def fake_search(uid, query, **kwargs):
        calls.update(uid=uid, query=query, **kwargs)
        return {"query": query, "items": [], "count": 0}
    monkeypatch.setattr(api, "search_user_workspace", fake_search)
    class FakeHandler:
        path = "/api/v1/search?q=contract&scopes=cases,documents&limit=12"
        def _send(self, status, payload):
            self.status, self.payload = status, payload
            return payload
    h=FakeHandler()
    h._unified_search=api.APIHandler._unified_search.__get__(h,FakeHandler)
    h._unified_search(77)
    assert h.status == 200
    assert calls["uid"] == 77
    assert calls["scopes"] == ["cases", "documents"]
    assert calls["limit"] == 12


def test_telegram_global_search_no_longer_calls_undefined_search_cases():
    source=(Path(__file__).resolve().parents[1]/"legal_bot"/"handlers.py").read_text(encoding="utf-8")
    assert "search_cases(uid, value, 20)" not in source
    assert "search_user_workspace" in source


def test_persian_normalization_handles_arabic_letters_zwnj_diacritics_and_digits(search_db):
    from legal_bot.unified_search import search_user_workspace
    with db.conn() as c:
        c.execute("UPDATE case_documents SET extracted_text=? WHERE id=10", ("موعد تحویلملک در ۱۴۰۵/۰۳/۱۲ تعیین شده است.",))
        c.commit()
    data = search_user_workspace(77, "موعد تحويل ملک در 1405/03/12", scopes=("documents",))
    assert data["count"] == 1
    assert data["items"][0]["page"] is None


def test_archived_material_is_excluded_by_default_and_included_only_on_request(search_db):
    default = search_user_workspace(77, "پرونده بایگانی", scopes=("cases",))
    archived = search_user_workspace(77, "پرونده بایگانی", scopes=("cases",), include_archived=True)
    assert default["count"] == 0
    assert archived["count"] == 1
    assert archived["items"][0]["case_id"] == 3


def test_page_and_line_provenance_is_taken_from_explicit_page_markers(search_db):
    with db.conn() as c:
        c.execute("UPDATE case_documents SET extracted_text=? WHERE id=10", (
            "مقدمه\n[صفحه ۲]\nموضوع قرارداد\nموعد تحویل ملک در خرداد\nپایان صفحه\n[صفحه ۴]\nضمیمه",))
        c.commit()
    data = search_user_workspace(77, "موعد تحویل ملک", scopes=("documents",))
    assert data["count"] == 1
    assert data["items"][0]["page"] == 2
    assert data["items"][0]["line"] == 3


def test_old_matching_document_is_not_hidden_by_a_recent_row_scan_cap(search_db):
    with db.conn() as c:
        c.executemany(
            "INSERT INTO case_documents(id,case_id,file_name,extracted_text,created_at) VALUES(?,?,?,?,?)",
            [(1000 + i, 1, f"غیرمرتبط-{i}.txt", f"متن عمومی و بدون تطبیق شماره {i}", "2026-01-05") for i in range(1250)],
        )
        c.execute("UPDATE case_documents SET extracted_text=? WHERE id=10", ("عبارت ویژه در سند قدیمی",))
        c.commit()
    data = search_user_workspace(77, "عبارت ویژه", scopes=("documents",), limit=60)
    assert any(x["source_id"] == 10 for x in data["items"])


def test_result_limit_is_applied_after_matching_and_newer_records_win_ties(search_db):
    with db.conn() as c:
        c.executemany(
            "INSERT INTO case_documents(id,case_id,file_name,extracted_text,created_at) VALUES(?,?,?,?,?)",
            [(20 + i, 1, f"سند-{i}.txt", "عبارت مشترک برای جست‌وجو", f"2026-02-{(i % 27) + 1:02d}") for i in range(8)],
        )
        c.commit()
    data = search_user_workspace(77, "عبارت مشترک", scopes=("documents",), limit=3)
    assert data["count"] == 3
    dates = [x["created_at"] for x in data["items"]]
    assert dates == sorted(dates, reverse=True)


def test_large_workspace_search_smoke_benchmark(search_db):
    import time
    with db.conn() as c:
        c.executemany(
            "INSERT INTO case_documents(id,case_id,file_name,extracted_text,created_at) VALUES(?,?,?,?,?)",
            [(3000 + i, 1, f"سند-آزمایشی-{i}.txt", f"متن آزمایشی قرارداد و تعهد شماره {i}", "2026-03-01") for i in range(2500)],
        )
        c.commit()
    started = time.perf_counter()
    data = search_user_workspace(77, "تعهد شماره 2499", scopes=("documents",), limit=20)
    elapsed = time.perf_counter() - started
    assert data["count"] >= 1
    assert elapsed < 5.0, f"synthetic 2,500-document search took {elapsed:.3f}s"


def test_api_archived_filter_is_forwarded_and_scope_is_allowlisted(monkeypatch):
    from legal_bot import api
    calls = {}
    def fake_search(uid, query, **kwargs):
        calls.update(uid=uid, query=query, **kwargs)
        return {"items": [], "count": 0}
    monkeypatch.setattr(api, "search_user_workspace", fake_search)
    class FakeHandler:
        path = "/api/v1/search?q=پرونده&scopes=cases&limit=999&archived=1"
        def _send(self, status, payload):
            self.status, self.payload = status, payload
            return payload
    h = FakeHandler()
    h._unified_search = api.APIHandler._unified_search.__get__(h, FakeHandler)
    h._unified_search(77)
    assert h.status == 200
    assert calls["uid"] == 77
    assert calls["scopes"] == ["cases"]
    assert calls["limit"] == 60
    assert calls["include_archived"] is True


def test_all_private_scopes_enforce_case_and_account_ownership(search_db):
    with db.conn() as c:
        c.execute("INSERT INTO case_lawyer_notes VALUES(?,?,?,?)", (2, 88, "عبارت محرمانه مالک دیگر", "2026-01-05"))
        c.execute("INSERT INTO case_tasks VALUES(?,?,?,?,?,?)", (2, 88, 2, "عبارت محرمانه مالک دیگر", "2026-01-06", "2026-01-05"))
        c.execute("INSERT INTO case_events VALUES(?,?,?,?,?,?)", (2, 88, 2, "عبارت محرمانه مالک دیگر", "جزئیات", "2026-01-05"))
        c.execute("INSERT INTO case_ai_history VALUES(?,?,?,?,?,?)", (2, 88, 2, "عبارت محرمانه مالک دیگر", "پاسخ خصوصی", "2026-01-05"))
        c.execute("INSERT INTO drafting_artifacts VALUES(?,?,?,?,?,?,?,?)", ("d88", 88, 2, "لایحه", "عبارت محرمانه مالک دیگر", 1, "2026-01-05", "2026-01-05"))
        c.execute("INSERT INTO clients VALUES(?,?,?,?,?,?,?)", (2, 88, "موکل مالک دیگر", "09120000000", "0012345678", "عبارت محرمانه مالک دیگر", "2026-01-05"))
        c.execute("INSERT INTO lawyer_library_items VALUES(?,?,?,?,?,?,?)", ("l88", 88, "قالب محرمانه", "قالب", "عبارت محرمانه مالک دیگر", "متن", "2026-01-05"))
        c.commit()
    data = search_user_workspace(
        77, "عبارت محرمانه مالک دیگر",
        scopes=("notes", "tasks", "ai", "drafts", "clients", "library"),
    )
    assert data["count"] == 0


def test_empty_scope_list_returns_no_private_results(search_db):
    data = search_user_workspace(77, "تحویل ملک", scopes=())
    assert data["items"] == []
    assert data["count"] == 0


def test_exact_phrase_ranks_above_loose_partial_token_matches(search_db):
    with db.conn() as c:
        c.executemany(
            "INSERT INTO case_documents(id,case_id,file_name,extracted_text,created_at) VALUES(?,?,?,?,?)",
            [
                (30, 1, "تطبیق جزئی", "تعهد شماره ۱۴۰۵ در قرارداد آمده است", "2026-02-01"),
                (31, 1, "تطبیق دقیق", "تعهد شماره ۱۴۰۵/۰۳/۱۲ در قرارداد آمده است", "2026-01-01"),
            ],
        )
        c.commit()
    data = search_user_workspace(77, "تعهد شماره ۱۴۰۵/۰۳/۱۲", scopes=("documents",), limit=10)
    assert data["items"][0]["source_id"] == 31


def test_total_count_and_source_counts_are_not_truncated_by_display_limit(search_db):
    with db.conn() as c:
        c.executemany(
            "INSERT INTO case_documents(id,case_id,file_name,extracted_text,created_at) VALUES(?,?,?,?,?)",
            [(60 + i, 1, f"سند مشترک-{i}", "عبارت مشترک در متن سند", f"2026-04-{(i % 27) + 1:02d}") for i in range(7)],
        )
        c.commit()
    data = search_user_workspace(77, "عبارت مشترک", scopes=("documents",), limit=3)
    assert data["count"] == 3
    assert data["total_count"] == 7
    assert data["source_counts"] == [{"kind": "documents", "label": "اسناد و نسخه‌ها", "count": 7}]
