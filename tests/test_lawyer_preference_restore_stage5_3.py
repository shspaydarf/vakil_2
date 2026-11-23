import sqlite3
import pytest

from legal_bot import config, lawyer_preference_store as store, lawyer_preference_service as service
from legal_bot.ai_preference_context import load_ai_preference_context


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    path = tmp_path / 'restore.db'
    monkeypatch.setattr(config, 'DB_PATH', path)
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE users(user_id INTEGER PRIMARY KEY)')
        conn.executemany('INSERT INTO users(user_id) VALUES(?)', [(1001,), (1002,)])
    store.init_lawyer_preference_tables()
    return path


def _save(owner, tone, version):
    return store.save_profile(owner, {'writing_style': {'tone': tone}},
                              expected_profile_version=version, confirm_save=True)


def test_restore_creates_new_version_and_preserves_original_history(isolated_db):
    _save(1001, 'formal', 0)       # v1
    _save(1001, 'neutral', 1)      # v2
    _save(1001, 'persuasive', 2)   # v3
    result = store.restore_profile_version(
        1001, source_profile_version=1, expected_profile_version=3, confirm_action=True)
    profile = store.get_profile(1001)
    history = store.list_profile_versions(1001)
    assert result['profile_version'] == 4
    assert result['source_profile_version'] == 1
    assert profile['profile_version'] == 4
    assert profile['preferences']['writing_style']['tone'] == 'formal'
    assert history[0]['change_type'] == 'restored'
    assert history[0]['profile_version'] == 4
    assert [x['profile_version'] for x in history] == [4, 3, 2, 1]
    assert [x['preferences']['writing_style']['tone'] for x in history[1:]] == ['persuasive', 'neutral', 'formal']


def test_restore_keeps_inactive_status_and_ai_context_off(isolated_db):
    _save(1001, 'formal', 0)
    _save(1001, 'neutral', 1)
    store.set_profile_status(1001, target_status='inactive', expected_profile_version=2, confirm_action=True)
    store.restore_profile_version(1001, source_profile_version=1,
                                  expected_profile_version=3, confirm_action=True)
    profile = store.get_profile(1001)
    assert profile['status'] == 'inactive'
    assert profile['preferences']['writing_style']['tone'] == 'formal'
    assert load_ai_preference_context(1001) == ''


def test_restore_active_profile_reaches_ai_after_restore(isolated_db):
    _save(1001, 'formal', 0)
    _save(1001, 'neutral', 1)
    store.restore_profile_version(1001, source_profile_version=1,
                                  expected_profile_version=2, confirm_action=True)
    assert 'رسمی' in load_ai_preference_context(1001)


def test_restore_requires_confirmation_and_current_version(isolated_db):
    _save(1001, 'formal', 0)
    with pytest.raises(store.ConfirmationRequired):
        store.restore_profile_version(1001, source_profile_version=1,
                                      expected_profile_version=1, confirm_action=False)
    with pytest.raises(store.ProfileVersionConflict):
        store.restore_profile_version(1001, source_profile_version=1,
                                      expected_profile_version=0, confirm_action=True)
    assert store.get_profile(1001)['profile_version'] == 1
    assert len(store.list_profile_versions(1001)) == 1


def test_restore_rejects_unknown_or_other_owner_snapshot(isolated_db):
    _save(1001, 'formal', 0)
    _save(1002, 'neutral', 0)
    with pytest.raises(store.ProfileVersionNotFound):
        store.restore_profile_version(1001, source_profile_version=999,
                                      expected_profile_version=1, confirm_action=True)
    with pytest.raises(store.ProfileVersionNotFound):
        store.restore_profile_version(1002, source_profile_version=2,
                                      expected_profile_version=1, confirm_action=True)


def test_restore_rejects_invalid_versions_and_missing_profile(isolated_db):
    _save(1001, 'formal', 0)
    for invalid in (0, -1, True, 'x'):
        with pytest.raises(ValueError):
            store.restore_profile_version(1001, source_profile_version=invalid,
                                          expected_profile_version=1, confirm_action=True)
    with pytest.raises(store.ProfileNotFound):
        store.restore_profile_version(1002, source_profile_version=1,
                                      expected_profile_version=1, confirm_action=True)


def test_restore_snapshot_failure_rolls_back_profile(isolated_db):
    _save(1001, 'formal', 0)
    _save(1001, 'neutral', 1)
    with sqlite3.connect(isolated_db) as conn:
        conn.execute("""CREATE TRIGGER fail_restore BEFORE INSERT ON lawyer_preference_versions
            WHEN NEW.change_type='restored'
            BEGIN SELECT RAISE(ABORT, 'forced restore failure'); END""")
    with pytest.raises(sqlite3.IntegrityError):
        store.restore_profile_version(1001, source_profile_version=1,
                                      expected_profile_version=2, confirm_action=True)
    profile = store.get_profile(1001)
    assert profile['profile_version'] == 2
    assert profile['preferences']['writing_style']['tone'] == 'neutral'
    assert len(store.list_profile_versions(1001)) == 2


def test_service_uses_authenticated_uid_and_ignores_payload_owner(isolated_db):
    _save(1001, 'formal', 0)
    _save(1001, 'neutral', 1)
    result = service.restore_editor_version(1001, {
        'owner_id': 1002, 'source_profile_version': 1,
        'expected_profile_version': 2, 'confirm_action': True,
    })
    assert result['profile']['profile_version'] == 3
    assert result['profile']['preferences']['writing_style']['tone'] == 'formal'
    assert store.get_profile(1002) is None


def test_restore_api_route_and_error_contract_are_registered():
    from pathlib import Path
    source = Path(__file__).resolve().parents[1].joinpath('legal_bot', 'api.py').read_text(encoding='utf-8')
    assert '/lawyer-preferences/restore' in source
    assert 'preference_version_not_found' in source
    assert 'def _lawyer_preferences_restore_action' in source
