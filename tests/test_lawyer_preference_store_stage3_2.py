import sqlite3

import pytest

from legal_bot import config
from legal_bot import lawyer_preference_store as store


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "memory-test.db"
    monkeypatch.setattr(config, "DB_PATH", db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE users(user_id INTEGER PRIMARY KEY)")
        conn.executemany("INSERT INTO users(user_id) VALUES(?)", [(101,), (202,)])
    store.init_lawyer_preference_tables()
    return db_path


def test_tables_are_additive_and_owner_fk_exists(isolated_db):
    with sqlite3.connect(isolated_db) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"users", "lawyer_preference_profiles", "lawyer_preference_versions"} <= tables
        fk = conn.execute("PRAGMA foreign_key_list(lawyer_preference_profiles)").fetchall()
        assert any(row[2] == "users" and row[3] == "user_id" for row in fk)


def test_save_and_load_confirmed_profile(isolated_db):
    saved = store.save_profile(101, {"writing_style": {"tone": "formal", "detail_level": "balanced"}}, expected_profile_version=0, confirm_save=True)
    loaded = store.get_profile(101)
    assert saved["profile_version"] == 1
    assert loaded["preferences"]["writing_style"]["tone"] == "formal"
    assert loaded["field_metadata"]["writing_style.tone"]["origin"] == "lawyer_entered"
    assert loaded["field_metadata"]["writing_style.tone"]["confirmed_at"]


def test_explicit_false_and_empty_profile_are_preserved(isolated_db):
    saved = store.save_profile(101, {"legal_analysis": {"counterargument_review": False}}, expected_profile_version=0, confirm_save=True)
    assert saved["preferences"]["legal_analysis"]["counterargument_review"] is False
    empty = store.save_profile(202, {}, expected_profile_version=0, confirm_save=True)
    assert empty["preferences"] == {}
    assert store.get_profile(202)["preferences"] == {}


def test_optimistic_version_conflict_does_not_overwrite(isolated_db):
    store.save_profile(101, {"writing_style": {"tone": "formal"}}, expected_profile_version=0, confirm_save=True)
    with pytest.raises(store.ProfileVersionConflict):
        store.save_profile(101, {"writing_style": {"tone": "neutral"}}, expected_profile_version=0, confirm_save=True)
    assert store.get_profile(101)["preferences"]["writing_style"]["tone"] == "formal"


def test_versions_are_immutable_snapshots_and_owner_scoped(isolated_db):
    store.save_profile(101, {"writing_style": {"tone": "formal"}}, expected_profile_version=0, confirm_save=True)
    store.save_profile(101, {"writing_style": {"tone": "neutral"}}, expected_profile_version=1, confirm_save=True)
    store.save_profile(202, {"writing_style": {"tone": "plain_language"}}, expected_profile_version=0, confirm_save=True)
    versions = store.list_profile_versions(101)
    assert [v["profile_version"] for v in versions] == [2, 1]
    assert versions[1]["preferences"]["writing_style"]["tone"] == "formal"
    assert len(store.list_profile_versions(202)) == 1


def test_save_requires_explicit_confirmation(isolated_db):
    with pytest.raises(store.ConfirmationRequired):
        store.save_profile(101, {}, expected_profile_version=0, confirm_save=False)
    assert store.get_profile(101) is None


def test_unconfirmed_origin_and_unknown_metadata_rejected(isolated_db):
    with pytest.raises(ValueError):
        store.save_profile(101, {"writing_style": {"tone": "formal"}}, expected_profile_version=0, confirm_save=True,
                           field_metadata={"writing_style.tone": {"origin": "ai_suggestion"}})
    with pytest.raises(ValueError):
        store.save_profile(101, {"writing_style": {"tone": "formal"}}, expected_profile_version=0, confirm_save=True,
                           field_metadata={"legal_analysis.secret": {"origin": "lawyer_entered"}})


def test_confirmed_suggestion_origin_is_recorded(isolated_db):
    saved = store.save_profile(101, {"writing_style": {"detail_level": "concise"}}, expected_profile_version=0, confirm_save=True,
        field_metadata={"writing_style.detail_level": {"origin": "lawyer_confirmed_suggestion"}})
    assert saved["field_metadata"]["writing_style.detail_level"]["origin"] == "lawyer_confirmed_suggestion"


def test_profile_and_snapshot_are_atomic(isolated_db):
    with sqlite3.connect(isolated_db) as conn:
        conn.execute("""CREATE TRIGGER fail_snapshot BEFORE INSERT ON lawyer_preference_versions
            BEGIN SELECT RAISE(ABORT, 'forced snapshot failure'); END""")
    with pytest.raises(sqlite3.IntegrityError):
        store.save_profile(101, {"writing_style": {"tone": "formal"}}, expected_profile_version=0, confirm_save=True)
    assert store.get_profile(101) is None


def test_bad_owner_and_nonexistent_user_are_rejected(isolated_db):
    with pytest.raises(ValueError):
        store.get_profile(0)
    with pytest.raises(sqlite3.IntegrityError):
        store.save_profile(999, {}, expected_profile_version=0, confirm_save=True)


def test_history_limit_is_bounded(isolated_db):
    store.save_profile(101, {}, expected_profile_version=0, confirm_save=True)
    assert len(store.list_profile_versions(101, limit=1000)) == 1
    assert store.list_profile_versions(101, limit=0) == store.list_profile_versions(101, limit=1)


