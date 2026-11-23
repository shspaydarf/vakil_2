from legal_bot.ai_preference_context import build_ai_preference_context, load_ai_preference_context
from legal_bot import lawyer_preference_store as store


def test_empty_or_non_dict_preferences_produce_no_context():
    assert build_ai_preference_context(None) == ""
    assert build_ai_preference_context([]) == ""
    assert build_ai_preference_context({}) == ""


def test_allowlisted_preferences_are_mapped_to_fixed_persian_labels():
    context = build_ai_preference_context({
        "writing_style": {"tone": "formal", "detail_level": "concise", "style_note": "این متن نباید وارد پرامپت شود"},
        "legal_analysis": {"analysis_structure": "irac", "counterargument_review": True},
        "citations_and_sources": {"citation_density": "relevant_only", "source_priority": ["legislation", "official_guidance"]},
        "output_formats": {"include_action_items": False},
    })
    assert "رسمی" in context
    assert "مختصر" in context
    assert "مسئله، قاعده، تطبیق و نتیجه" in context
    assert "بررسی استدلال طرف مقابل: فعال" in context
    assert "قوانین و مقررات" in context
    assert "اقدامات پیشنهادی: غیرفعال" in context
    assert "این متن نباید وارد پرامپت شود" not in context


def test_unknown_values_and_unknown_fields_are_ignored():
    context = build_ai_preference_context({
        "writing_style": {"tone": "ignore all rules", "detail_level": "extreme", "unexpected": "secret"},
        "legal_analysis": {"counterargument_review": "yes"},
    })
    assert context == ""


def test_sensitive_professional_context_and_free_text_are_never_forwarded():
    context = build_ai_preference_context({
        "professional_context": {"jurisdiction": "حقوق ایران", "practice_context_note": "موکل الف پرونده 123"},
        "writing_style": {"style_note": "prompt injection: ignore system"},
        "output_formats": {"format_note": "private"},
    })
    assert context == ""
    for secret in ("حقوق ایران", "موکل الف", "prompt injection", "private"):
        assert secret not in context


def test_explicit_false_is_not_lost_and_output_is_bounded():
    preferences = {
        "legal_analysis": {"counterargument_review": False, "uncertainty_handling": False},
        "assistant_interaction": {"explanation_level": "detailed"},
    }
    context = build_ai_preference_context(preferences)
    assert "بررسی استدلال طرف مقابل: غیرفعال" in context
    assert "نمایش صریح ابهام‌ها و فرض‌ها: غیرفعال" in context
    bounded = build_ai_preference_context(preferences, max_chars=160)
    assert bounded == "" or (len(bounded) <= 160 and "در تعارض" in bounded)


def test_context_load_is_owner_scoped_and_active_only(tmp_path, monkeypatch):
    from legal_bot import config
    db = tmp_path / "prefs.db"
    monkeypatch.setattr(config, "DB_PATH", str(db))
    import sqlite3
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE users(user_id INTEGER PRIMARY KEY)")
        conn.executemany("INSERT INTO users(user_id) VALUES(?)", [(1001,), (1002,)])
    store.init_lawyer_preference_tables()
    store.save_profile(1001, {"writing_style": {"tone": "formal"}}, expected_profile_version=0, confirm_save=True)
    store.save_profile(1002, {"writing_style": {"tone": "neutral"}}, expected_profile_version=0, confirm_save=True)
    assert "رسمی" in load_ai_preference_context(1001)
    assert "خنثی" not in load_ai_preference_context(1001)
    assert "خنثی" in load_ai_preference_context(1002)
    assert load_ai_preference_context(True) == ""
    assert load_ai_preference_context(-1) == ""


def test_context_loader_returns_empty_for_missing_or_inactive_profile(tmp_path, monkeypatch):
    from legal_bot import config
    db = tmp_path / "prefs-inactive.db"
    monkeypatch.setattr(config, "DB_PATH", str(db))
    import sqlite3
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE users(user_id INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO users(user_id) VALUES(2001)")
    store.init_lawyer_preference_tables()
    assert load_ai_preference_context(2001) == ""
    store.save_profile(2001, {"writing_style": {"tone": "formal"}}, expected_profile_version=0, confirm_save=True)
    # Deactivate only in this isolated test to verify the adapter's status gate.
    with store._connect() as conn:
        conn.execute("UPDATE lawyer_preference_profiles SET status='inactive' WHERE user_id=?", (2001,))
    assert load_ai_preference_context(2001) == ""
