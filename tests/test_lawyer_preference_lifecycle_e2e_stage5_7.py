"""Stage 5.7 end-to-end checks for the lawyer-memory lifecycle contract."""
import sqlite3

import pytest

from legal_bot import config, lawyer_preference_store as store
from legal_bot.ai_preference_context import load_ai_preference_context


@pytest.fixture

def lifecycle_db(tmp_path, monkeypatch):
    path = tmp_path / "lifecycle-e2e.db"
    monkeypatch.setattr(config, "DB_PATH", path)
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE users(user_id INTEGER PRIMARY KEY)")
        conn.executemany("INSERT INTO users(user_id) VALUES(?)", [(7101,), (7102,)])
    store.init_lawyer_preference_tables()
    return path


def _save(uid, tone, expected):
    return store.save_profile(
        uid, {"writing_style": {"tone": tone}},
        expected_profile_version=expected, confirm_save=True,
    )


def test_full_lifecycle_save_deactivate_restore_compare_activate_delete_recreate(lifecycle_db):
    # Save two revisions; only the active revision reaches AI.
    _save(7101, "formal", 0)      # v1
    _save(7101, "neutral", 1)     # v2
    assert "رسمی" not in load_ai_preference_context(7101)
    assert "خنثی" in load_ai_preference_context(7101)

    # Deactivation keeps data/history but removes AI preference injection.
    store.set_profile_status(7101, target_status="inactive", expected_profile_version=2, confirm_action=True)  # v3
    assert store.get_profile(7101)["preferences"]["writing_style"]["tone"] == "neutral"
    assert load_ai_preference_context(7101) == ""

    # Restore v1 as v4 without reactivating the profile or rewriting old rows.
    store.restore_profile_version(7101, source_profile_version=1,
                                  expected_profile_version=3, confirm_action=True)
    current = store.get_profile(7101)
    assert current["profile_version"] == 4
    assert current["status"] == "inactive"
    assert current["preferences"]["writing_style"]["tone"] == "formal"
    assert load_ai_preference_context(7101) == ""

    # Comparison is directional/read-only; activation exposes restored preferences.
    diff = store.compare_profile_versions(7101, from_profile_version=1, to_profile_version=2)
    assert diff["change_count"] == 1
    assert diff["changes"][0]["change_type"] == "changed"
    store.set_profile_status(7101, target_status="active", expected_profile_version=4, confirm_action=True)  # v5
    assert "رسمی" in load_ai_preference_context(7101)

    # Hard delete removes both current profile and all snapshots; recreation starts at v1.
    deleted = store.hard_delete_profile(7101, expected_profile_version=5, confirm_action=True)
    assert deleted["deleted"] is True
    assert store.get_profile(7101) is None
    assert store.list_profile_versions(7101) == []
    assert load_ai_preference_context(7101) == ""
    recreated = _save(7101, "neutral", 0)
    assert recreated["profile_version"] == 1
    assert [row["profile_version"] for row in store.list_profile_versions(7101)] == [1]


def test_full_lifecycle_isolation_between_two_lawyers(lifecycle_db):
    _save(7101, "formal", 0)
    _save(7102, "neutral", 0)
    _save(7102, "formal", 1)  # v2 exists only for the other lawyer
    assert "رسمی" in load_ai_preference_context(7101)
    assert "رسمی" in load_ai_preference_context(7102)
    with pytest.raises(store.ProfileVersionNotFound):
        store.compare_profile_versions(7101, from_profile_version=1, to_profile_version=2)
    store.set_profile_status(7101, target_status="inactive", expected_profile_version=1, confirm_action=True)
    assert load_ai_preference_context(7101) == ""
    store.hard_delete_profile(7101, expected_profile_version=2, confirm_action=True)
    assert store.get_profile(7102)["preferences"]["writing_style"]["tone"] == "formal"
    assert len(store.list_profile_versions(7102)) == 2


def test_stale_version_and_failed_snapshot_do_not_partially_mutate(lifecycle_db):
    _save(7101, "formal", 0)
    _save(7101, "neutral", 1)
    with pytest.raises(store.ProfileVersionConflict):
        store.set_profile_status(7101, target_status="inactive", expected_profile_version=1, confirm_action=True)
    with sqlite3.connect(lifecycle_db) as conn:
        conn.execute("""CREATE TRIGGER fail_restore_e2e BEFORE INSERT ON lawyer_preference_versions
            WHEN NEW.change_type='restored'
            BEGIN SELECT RAISE(ABORT, 'forced e2e restore failure'); END""")
    with pytest.raises(sqlite3.IntegrityError):
        store.restore_profile_version(7101, source_profile_version=1,
                                      expected_profile_version=2, confirm_action=True)
    profile = store.get_profile(7101)
    assert profile["profile_version"] == 2
    assert profile["status"] == "active"
    assert profile["preferences"]["writing_style"]["tone"] == "neutral"
    assert len(store.list_profile_versions(7101)) == 2
