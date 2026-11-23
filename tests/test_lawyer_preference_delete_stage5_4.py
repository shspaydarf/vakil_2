import sqlite3
import pytest

from legal_bot import config, lawyer_preference_store as store
from legal_bot import lawyer_preference_service as service
from legal_bot.ai_preference_context import load_ai_preference_context


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    path = tmp_path / 'hard-delete.db'
    monkeypatch.setattr(config, 'DB_PATH', path)
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE users(user_id INTEGER PRIMARY KEY)')
        conn.executemany('INSERT INTO users(user_id) VALUES(?)', [(1001,), (1002,)])
    store.init_lawyer_preference_tables()
    return path


def _save(owner, tone, version):
    return store.save_profile(owner, {'writing_style': {'tone': tone}},
                              expected_profile_version=version, confirm_save=True)


def test_hard_delete_removes_profile_and_all_history_atomically(isolated_db):
    _save(1001, 'formal', 0)
    _save(1001, 'neutral', 1)
    store.set_profile_status(1001, target_status='inactive', expected_profile_version=2, confirm_action=True)
    result = store.hard_delete_profile(1001, expected_profile_version=3, confirm_action=True)
    assert result == {'deleted': True, 'deleted_versions': 3}
    assert store.get_profile(1001) is None
    assert store.list_profile_versions(1001) == []
    assert load_ai_preference_context(1001) == ''


def test_delete_is_owner_scoped_and_other_owner_is_untouched(isolated_db):
    _save(1001, 'formal', 0)
    _save(1002, 'neutral', 0)
    store.hard_delete_profile(1001, expected_profile_version=1, confirm_action=True)
    assert store.get_profile(1001) is None
    assert store.get_profile(1002)['preferences']['writing_style']['tone'] == 'neutral'
    assert len(store.list_profile_versions(1002)) == 1


def test_delete_requires_confirmation_and_expected_current_version(isolated_db):
    _save(1001, 'formal', 0)
    _save(1001, 'neutral', 1)
    with pytest.raises(store.ConfirmationRequired):
        store.hard_delete_profile(1001, expected_profile_version=2, confirm_action=False)
    with pytest.raises(store.ProfileVersionConflict):
        store.hard_delete_profile(1001, expected_profile_version=1, confirm_action=True)
    assert store.get_profile(1001) is not None
    assert len(store.list_profile_versions(1001)) == 2


def test_delete_rejects_missing_profile_and_invalid_version(isolated_db):
    with pytest.raises(store.ProfileNotFound):
        store.hard_delete_profile(1001, expected_profile_version=1, confirm_action=True)
    _save(1001, 'formal', 0)
    for invalid in (0, -1, True, 'x'):
        with pytest.raises(ValueError):
            store.hard_delete_profile(1001, expected_profile_version=invalid, confirm_action=True)


def test_delete_stops_on_history_integrity_mismatch(isolated_db):
    _save(1001, 'formal', 0)
    with sqlite3.connect(isolated_db) as conn:
        conn.execute('DELETE FROM lawyer_preference_versions WHERE user_id=1001')
    with pytest.raises(store.ProfileIntegrityError):
        store.hard_delete_profile(1001, expected_profile_version=1, confirm_action=True)
    assert store.get_profile(1001) is not None


def test_delete_failure_rolls_back_both_tables(isolated_db):
    _save(1001, 'formal', 0)
    with sqlite3.connect(isolated_db) as conn:
        conn.execute("""CREATE TRIGGER fail_profile_delete BEFORE DELETE ON lawyer_preference_profiles
            BEGIN SELECT RAISE(ABORT, 'forced delete failure'); END""")
    with pytest.raises(sqlite3.IntegrityError):
        store.hard_delete_profile(1001, expected_profile_version=1, confirm_action=True)
    assert store.get_profile(1001) is not None
    assert len(store.list_profile_versions(1001)) == 1


def test_delete_service_uses_authenticated_uid_not_payload_owner(isolated_db):
    _save(1001, 'formal', 0)
    _save(1002, 'neutral', 0)
    result = service.delete_editor_profile(1001, {
        'owner_id': 1002, 'expected_profile_version': 1, 'confirm_action': True,
    })
    assert result['deleted'] is True
    assert store.get_profile(1001) is None
    assert store.get_profile(1002)['preferences']['writing_style']['tone'] == 'neutral'


def test_recreate_after_hard_delete_starts_at_version_one(isolated_db):
    _save(1001, 'formal', 0)
    store.hard_delete_profile(1001, expected_profile_version=1, confirm_action=True)
    recreated = _save(1001, 'neutral', 0)
    assert recreated['profile_version'] == 1
    assert [x['profile_version'] for x in store.list_profile_versions(1001)] == [1]


def test_delete_api_route_is_registered():
    from pathlib import Path
    source = Path(__file__).resolve().parents[1].joinpath('legal_bot', 'api.py').read_text(encoding='utf-8')
    assert '/lawyer-preferences/profile' in source
    assert 'delete_editor_profile' in source
    assert 'preference_integrity_conflict' in source
