from legal_bot import ai


def test_call_feature_injects_owner_scoped_preferences_before_user(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        'legal_bot.ai_preference_context.load_ai_preference_context',
        lambda uid, **kwargs: f'PREFERENCE-FOR-{uid}',
    )
    monkeypatch.setattr(ai, '_call', lambda messages, temperature=0.05: captured.update(messages=messages) or 'ok')

    result = ai._call_feature([
        {'role': 'system', 'content': 'SYSTEM-RULES'},
        {'role': 'user', 'content': 'USER-REQUEST'},
    ], preference_uid=731)

    assert result == 'ok'
    assert [m['role'] for m in captured['messages']] == ['system', 'system', 'user']
    assert captured['messages'][0]['content'] == 'SYSTEM-RULES'
    assert captured['messages'][1]['content'] == 'PREFERENCE-FOR-731'
    assert captured['messages'][2]['content'] == 'USER-REQUEST'


def test_call_feature_without_authenticated_uid_keeps_legacy_messages(monkeypatch):
    captured = {}
    monkeypatch.setattr(ai, '_call', lambda messages, temperature=0.05: captured.update(messages=messages) or 'ok')
    original = [{'role': 'system', 'content': 'SYSTEM'}, {'role': 'user', 'content': 'USER'}]

    ai._call_feature(original)

    assert captured['messages'] == original


def test_preference_storage_failure_does_not_block_ai(monkeypatch):
    captured = {}
    def fail(_uid, **kwargs):
        raise RuntimeError('storage unavailable')
    monkeypatch.setattr('legal_bot.ai_preference_context.load_ai_preference_context', fail)
    monkeypatch.setattr(ai, '_call', lambda messages, temperature=0.05: captured.update(messages=messages) or 'ok')

    assert ai._call_feature([{'role': 'user', 'content': 'USER'}], preference_uid=731) == 'ok'
    assert captured['messages'] == [{'role': 'user', 'content': 'USER'}]
