import sqlite3
import pytest

from legal_bot import config, lawyer_preference_store as store
from legal_bot import lawyer_preference_service as service


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    path = tmp_path / 'history-compare.db'
    monkeypatch.setattr(config, 'DB_PATH', path)
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE users(user_id INTEGER PRIMARY KEY)')
        conn.executemany('INSERT INTO users(user_id) VALUES(?)', [(1001,), (1002,)])
    store.init_lawyer_preference_tables()
    return path


def _save(owner, preferences, version):
    return store.save_profile(owner, preferences, expected_profile_version=version, confirm_save=True)


def test_compare_reports_added_removed_and_changed_fields(isolated_db):
    _save(1001, {'writing_style': {'tone': 'formal', 'detail_level': 'concise'}, 'professional_context': {'jurisdiction': 'حقوق ایران'}}, 0)
    _save(1001, {'writing_style': {'tone': 'neutral'}, 'legal_analysis': {'risk_focus': 'high'}}, 1)
    result = store.compare_profile_versions(1001, from_profile_version=1, to_profile_version=2)
    assert result['change_count'] == 4
    changes = {item['field']: item for item in result['changes']}
    assert changes['writing_style.tone']['change_type'] == 'changed'
    assert changes['writing_style.detail_level']['change_type'] == 'removed'
    assert changes['legal_analysis.risk_focus']['change_type'] == 'added'
    assert changes['professional_context.jurisdiction']['change_type'] == 'removed'


def test_compare_is_directional_and_does_not_mutate_snapshots(isolated_db):
    _save(1001, {'writing_style': {'tone': 'formal'}}, 0)
    _save(1001, {'writing_style': {'tone': 'neutral'}}, 1)
    forward = store.compare_profile_versions(1001, from_profile_version=1, to_profile_version=2)
    backward = store.compare_profile_versions(1001, from_profile_version=2, to_profile_version=1)
    assert forward['changes'][0]['before'] == 'formal'
    assert forward['changes'][0]['after'] == 'neutral'
    assert backward['changes'][0]['before'] == 'neutral'
    assert backward['changes'][0]['after'] == 'formal'
    assert [x['profile_version'] for x in store.list_profile_versions(1001)] == [2, 1]


def test_compare_owner_scoped_and_missing_versions_are_not_disclosed(isolated_db):
    _save(1001, {'writing_style': {'tone': 'formal'}}, 0)
    _save(1002, {'writing_style': {'tone': 'neutral'}}, 0)
    with pytest.raises(store.ProfileVersionNotFound):
        store.compare_profile_versions(1001, from_profile_version=1, to_profile_version=2)


def test_compare_rejects_same_or_invalid_versions(isolated_db):
    _save(1001, {'writing_style': {'tone': 'formal'}}, 0)
    for a, b in ((1, 1), (0, 1), (True, 2), ('bad', 2)):
        with pytest.raises(ValueError):
            store.compare_profile_versions(1001, from_profile_version=a, to_profile_version=b)


def test_service_uses_authenticated_uid_not_payload_owner(isolated_db):
    _save(1001, {'writing_style': {'tone': 'formal'}}, 0)
    _save(1001, {'writing_style': {'tone': 'neutral'}}, 1)
    result = service.compare_history(1001, {
        'owner_id': 1002, 'from_profile_version': 1, 'to_profile_version': 2,
    })
    assert result['change_count'] == 1
    assert store.get_profile(1002) is None


def test_history_limit_is_bounded_and_keeps_newest_first(isolated_db):
    for i in range(1, 4):
        _save(1001, {'writing_style': {'tone': ('formal' if i % 2 else 'neutral')}}, i - 1)
    history = service.list_history(1001, limit=999)
    assert len(history) == 3
    assert [x['profile_version'] for x in history] == [3, 2, 1]


def test_compare_route_is_registered():
    from pathlib import Path
    source = Path(__file__).resolve().parents[1].joinpath('legal_bot', 'api.py').read_text(encoding='utf-8')
    assert '/lawyer-preferences/compare' in source
    assert 'compare_history' in source
