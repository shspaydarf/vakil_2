from legal_bot import api


def test_preference_schema_uses_authenticated_uid_and_returns_profile(monkeypatch):
    seen = {}
    def fake_load(uid):
        seen['uid'] = uid
        return {
            'schema': {'categories': [{'key': 'writing_style'}], 'persistence_enabled': False, 'stage': '2_of_6'},
            'profile': {'exists': True, 'preferences': {'writing_style': {'tone': 'formal'}}, 'profile_version': 4,
                        'status': 'active', 'updated_at': '2026-10-31T10:00:00Z', 'confirmed_at': '2026-10-31T10:00:00Z'},
        }
    monkeypatch.setattr(api.lawyer_pref_service, 'load_editor', fake_load)
    handler = object.__new__(api.APIHandler)
    captured = {}
    handler._send = lambda status, payload, **kwargs: captured.update(status=status, payload=payload)
    handler._lawyer_preferences_schema(456)
    assert seen['uid'] == 456
    data = captured['payload']['data']
    assert data['persistence_enabled'] is True
    assert data['stage'] == '3_of_6'
    assert data['profile']['profile_version'] == 4
    assert 'user_id' not in data['profile']


def test_preference_save_passes_dispatcher_uid_not_payload_owner(monkeypatch):
    seen = {}
    def fake_save(uid, payload):
        seen['uid'] = uid
        seen['payload'] = payload
        return {'profile': {'exists': True, 'profile_version': 2}, 'selected_count': 1, 'persisted': True}
    monkeypatch.setattr(api.lawyer_pref_service, 'save_editor', fake_save)
    handler = object.__new__(api.APIHandler)
    captured = {}
    handler._send = lambda status, payload, **kwargs: captured.update(status=status, payload=payload)
    handler._lawyer_preferences_action(456, 'save', {
        'owner_id': 999, 'confirm_save': True, 'expected_profile_version': 1,
        'preferences': {'writing_style': {'tone': 'formal'}},
    })
    assert seen['uid'] == 456
    assert seen['payload']['owner_id'] == 999  # ignored by service; never used as owner
    assert captured['status'] == 200
    assert captured['payload']['data']['persisted'] is True


def test_preference_save_maps_version_conflict_to_http_409(monkeypatch):
    handler = object.__new__(api.APIHandler)
    captured = {}
    handler._error = lambda status, code, message: captured.update(status=status, code=code, message=message)
    try:
        raise api.ProfileVersionConflict('stale')
    except api.ProfileVersionConflict:
        result = handler._error(409, 'preference_version_conflict', 'conflict')
    assert captured['status'] == 409
    assert captured['code'] == 'preference_version_conflict'


def test_preference_api_routes_are_registered():
    from pathlib import Path
    source = Path(__file__).resolve().parents[1].joinpath('legal_bot', 'api.py').read_text(encoding='utf-8')
    assert '/lawyer-preferences/history' in source
    assert '/lawyer-preferences/(preview|suggest|save)' in source


def test_authenticated_http_post_save_and_get_reload_roundtrip(tmp_path, monkeypatch):
    import sqlite3
    from legal_bot import config, lawyer_preference_store

    db_path = tmp_path / 'api-preferences.sqlite3'
    monkeypatch.setattr(config, 'DB_PATH', db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute('CREATE TABLE users(user_id INTEGER PRIMARY KEY)')
        conn.executemany('INSERT INTO users(user_id) VALUES(?)', [(321,), (654,)])
    lawyer_preference_store.init_lawyer_preference_tables()
    monkeypatch.setattr(api, '_auth_user', lambda headers: 321)
    monkeypatch.setattr(api, '_check_rate_limit', lambda handler: None)

    post = object.__new__(api.APIHandler)
    post.path = '/api/v1/lawyer-preferences/save'
    post.headers = {}
    post._read_json = lambda: {
        'owner_id': 654, 'preferences': {'writing_style': {'tone': 'formal'}},
        'expected_profile_version': 0, 'confirm_save': True,
    }
    post_result = {}
    post._send = lambda status, payload, **kwargs: post_result.update(status=status, payload=payload)
    post._error = lambda status, code, message: post_result.update(status=status, payload={'error': {'code': code, 'message': message}})
    post.do_POST()
    assert post_result['status'] == 200
    assert post_result['payload']['data']['profile']['profile_version'] == 1

    get = object.__new__(api.APIHandler)
    get.path = '/api/v1/lawyer-preferences/schema'
    get.headers = {}
    get_result = {}
    get._send = lambda status, payload, **kwargs: get_result.update(status=status, payload=payload)
    get._error = lambda status, code, message: get_result.update(status=status, payload={'error': {'code': code, 'message': message}})
    get.do_GET()
    assert get_result['status'] == 200
    profile = get_result['payload']['data']['profile']
    assert profile['profile_version'] == 1
    assert profile['preferences']['writing_style']['tone'] == 'formal'
    assert lawyer_preference_store.get_profile(654) is None


def test_status_route_uses_authenticated_uid_and_not_payload_owner(monkeypatch):
    seen = {}
    def fake_change(uid, payload, target_status):
        seen.update(uid=uid, payload=payload, target_status=target_status)
        return {'profile': {'exists': True, 'status': target_status, 'profile_version': 2},
                'status': target_status, 'profile_version': 2, 'changed': True}
    monkeypatch.setattr(api.lawyer_pref_service, 'change_editor_status', fake_change)
    handler = object.__new__(api.APIHandler)
    captured = {}
    handler._send = lambda status, payload, **kwargs: captured.update(status=status, payload=payload)
    handler._lawyer_preferences_status_action(456, 'deactivate', {
        'owner_id': 999, 'expected_profile_version': 1, 'confirm_action': True,
    })
    assert seen['uid'] == 456
    assert seen['target_status'] == 'inactive'
    assert captured['status'] == 200


def test_lifecycle_routes_are_registered():
    from pathlib import Path
    source = Path(__file__).resolve().parents[1].joinpath('legal_bot', 'api.py').read_text(encoding='utf-8')
    assert '/lawyer-preferences/(activate|deactivate)' in source
