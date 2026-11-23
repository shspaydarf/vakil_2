import sqlite3
import pytest

from legal_bot import config, lawyer_preference_store as store
from legal_bot.ai_preference_context import load_ai_preference_context


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    path = tmp_path / 'lifecycle.db'
    monkeypatch.setattr(config, 'DB_PATH', path)
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE users(user_id INTEGER PRIMARY KEY)')
        conn.executemany('INSERT INTO users(user_id) VALUES(?)', [(1001,), (1002,)])
    store.init_lawyer_preference_tables()
    return path


def test_deactivate_and_activate_append_versions_and_preserve_preferences(isolated_db):
    store.save_profile(1001, {'writing_style': {'tone': 'formal'}}, expected_profile_version=0, confirm_save=True)
    deactivated = store.set_profile_status(1001, target_status='inactive', expected_profile_version=1, confirm_action=True)
    assert deactivated == {'profile_version': 2, 'status': 'inactive', 'changed': True, 'updated_at': deactivated['updated_at']}
    assert store.get_profile(1001)['preferences']['writing_style']['tone'] == 'formal'
    assert load_ai_preference_context(1001) == ''

    activated = store.set_profile_status(1001, target_status='active', expected_profile_version=2, confirm_action=True)
    assert activated['profile_version'] == 3
    assert activated['status'] == 'active'
    assert 'رسمی' in load_ai_preference_context(1001)
    history = store.list_profile_versions(1001)
    assert [(x['profile_version'], x['change_type']) for x in history] == [
        (3, 'activated'), (2, 'deactivated'), (1, 'created')]
    assert all(x['preferences']['writing_style']['tone'] == 'formal' for x in history)


def test_same_status_is_idempotent_without_extra_version(isolated_db):
    store.save_profile(1001, {}, expected_profile_version=0, confirm_save=True)
    result = store.set_profile_status(1001, target_status='active', expected_profile_version=1, confirm_action=True)
    assert result['changed'] is False
    assert result['profile_version'] == 1
    assert len(store.list_profile_versions(1001)) == 1


def test_status_change_requires_confirmation_and_current_version(isolated_db):
    store.save_profile(1001, {}, expected_profile_version=0, confirm_save=True)
    with pytest.raises(store.ConfirmationRequired):
        store.set_profile_status(1001, target_status='inactive', expected_profile_version=1, confirm_action=False)
    with pytest.raises(store.ProfileVersionConflict):
        store.set_profile_status(1001, target_status='inactive', expected_profile_version=0, confirm_action=True)
    assert store.get_profile(1001)['status'] == 'active'
    assert len(store.list_profile_versions(1001)) == 1


def test_missing_profile_and_invalid_target_rejected(isolated_db):
    with pytest.raises(store.ProfileNotFound):
        store.set_profile_status(1001, target_status='inactive', expected_profile_version=1, confirm_action=True)
    with pytest.raises(ValueError):
        store.set_profile_status(1001, target_status='deleted', expected_profile_version=1, confirm_action=True)


def test_status_mutation_is_owner_scoped_and_atomic(isolated_db):
    store.save_profile(1001, {'writing_style': {'tone': 'formal'}}, expected_profile_version=0, confirm_save=True)
    store.save_profile(1002, {'writing_style': {'tone': 'neutral'}}, expected_profile_version=0, confirm_save=True)
    store.set_profile_status(1001, target_status='inactive', expected_profile_version=1, confirm_action=True)
    assert store.get_profile(1001)['status'] == 'inactive'
    assert store.get_profile(1002)['status'] == 'active'
    assert len(store.list_profile_versions(1002)) == 1


def test_snapshot_failure_rolls_back_profile_status(isolated_db):
    store.save_profile(1001, {}, expected_profile_version=0, confirm_save=True)
    with sqlite3.connect(isolated_db) as conn:
        conn.execute("""CREATE TRIGGER fail_lifecycle_snapshot BEFORE INSERT ON lawyer_preference_versions
            WHEN NEW.change_type='deactivated'
            BEGIN SELECT RAISE(ABORT, 'forced lifecycle snapshot failure'); END""")
    with pytest.raises(sqlite3.IntegrityError):
        store.set_profile_status(1001, target_status='inactive', expected_profile_version=1, confirm_action=True)
    assert store.get_profile(1001)['status'] == 'active'
    assert store.get_profile(1001)['profile_version'] == 1
    assert len(store.list_profile_versions(1001)) == 1
