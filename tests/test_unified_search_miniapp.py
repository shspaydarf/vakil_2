from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_homepage_has_global_search_launcher_and_privacy_copy():
    html = (ROOT / "miniapp" / "index.html").read_text(encoding="utf-8")
    assert 'id="globalSearchForm"' in html
    assert 'id="globalSearchInput"' in html
    assert 'id="globalSearchOptions"' in html
    assert 'id="globalSearchArchived"' in html
    assert "بدون ارسال متن پرونده به AI خارجی" in html


def test_global_search_ui_uses_unified_api_and_displays_provenance_fields():
    js = (ROOT / "miniapp" / "app.js").read_text(encoding="utf-8")
    assert "/api/v1/search?q=" in js
    assert "data.source_counts" in js
    assert "x.case_name" in js
    assert "x.page" in js
    assert "x.line" in js
    assert "x.locator" in js
    assert "data.privacy_note" in js


def test_global_search_has_all_supported_scopes_and_archived_filter():
    js = (ROOT / "miniapp" / "app.js").read_text(encoding="utf-8")
    for scope in ("cases", "documents", "notes", "tasks", "ai", "drafts", "clients", "library", "laws", "glossary"):
        assert f'{scope}:"' in js
    assert "includeArchived" in js
    assert "unifiedSearchArchived" in js


def test_global_search_ui_discloses_when_results_are_truncated():
    js = (ROOT / "miniapp" / "app.js").read_text(encoding="utf-8")
    assert "data.total_count>data.count" in js
    assert "نمایش ${faNum(data.count||0)} از ${faNum(data.total_count)} نتیجه" in js
