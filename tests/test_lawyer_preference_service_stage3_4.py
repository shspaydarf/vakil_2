import sqlite3
import pytest

from legal_bot import config
from legal_bot import lawyer_preference_service as service
from legal_bot import lawyer_preference_store as store


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    path = tmp_path / "service.db"
    monkeypatch.setattr(config, "DB_PATH", path)
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE users(user_id INTEGER PRIMARY KEY)")
        conn.executemany("INSERT INTO users(user_id) VALUES(?)", [(101,), (202,)])
    store.init_lawyer_preference_tables()
    return path


def test_load_editor_returns_empty_form_state_for_new_lawyer(isolated_db):
    result = service.load_editor(101)
    assert result["profile"] == {
        "exists": False, "preferences": {}, "profile_version": 0,
        "status": "not_created", "updated_at": None, "confirmed_at": None,
    }
    assert len(result["schema"]["categories"]) == 7


def test_save_and_reload_existing_form_values(isolated_db):
    result = service.save_editor(101, {
        "preferences": {"writing_style": {"tone": "formal"}, "legal_analysis": {"counterargument_review": False}},
        "expected_profile_version": 0, "confirm_save": True,
    })
    assert result["persisted"] is True
    assert result["profile"]["profile_version"] == 1
    loaded = service.load_editor(101)["profile"]
    assert loaded["preferences"]["writing_style"]["tone"] == "formal"
    assert loaded["preferences"]["legal_analysis"]["counterargument_review"] is False


def test_suggestion_is_only_recorded_as_confirmed_when_field_is_listed(isolated_db):
    service.save_editor(101, {
        "preferences": {"writing_style": {"detail_level": "concise", "tone": "formal"}},
        "expected_profile_version": 0, "confirm_save": True,
        "confirmed_suggestion_fields": ["writing_style.detail_level"],
    })
    profile = store.get_profile(101)
    assert profile["field_metadata"]["writing_style.detail_level"]["origin"] == "lawyer_confirmed_suggestion"
    assert profile["field_metadata"]["writing_style.tone"]["origin"] == "lawyer_entered"


def test_no_save_without_explicit_confirmation(isolated_db):
    with pytest.raises(store.ConfirmationRequired):
        service.save_editor(101, {"preferences": {}, "expected_profile_version": 0})
    assert store.get_profile(101) is None


def test_version_conflict_prevents_lost_update(isolated_db):
    service.save_editor(101, {"preferences": {"writing_style": {"tone": "formal"}}, "expected_profile_version": 0, "confirm_save": True})
    with pytest.raises(store.ProfileVersionConflict):
        service.save_editor(101, {"preferences": {"writing_style": {"tone": "neutral"}}, "expected_profile_version": 0, "confirm_save": True})
    assert service.load_editor(101)["profile"]["preferences"]["writing_style"]["tone"] == "formal"


def test_owner_isolation_and_no_client_owner_field(isolated_db):
    service.save_editor(101, {"preferences": {"writing_style": {"tone": "formal"}}, "expected_profile_version": 0, "confirm_save": True})
    assert service.load_editor(202)["profile"]["exists"] is False
    # Extra owner_id in form payload is ignored; service owner comes from caller.
    service.save_editor(202, {"owner_id": 101, "preferences": {}, "expected_profile_version": 0, "confirm_save": True})
    assert store.get_profile(101)["preferences"]["writing_style"]["tone"] == "formal"
    assert store.get_profile(202)["preferences"] == {}


def test_preview_is_non_persistent_and_privacy_screened(isolated_db):
    preview = service.preview_editor({"writing_style": {"tone": "formal"}})
    assert preview["persisted"] is False and preview["selected_count"] == 1
    assert store.get_profile(101) is None
    with pytest.raises(store.PreferencePrivacyError):
        service.preview_editor({"writing_style": {"style_note": "تماس 09123456789"}})


def test_history_is_owner_scoped(isolated_db):
    service.save_editor(101, {"preferences": {}, "expected_profile_version": 0, "confirm_save": True})
    assert len(service.list_history(101)) == 1
    assert service.list_history(202) == []
