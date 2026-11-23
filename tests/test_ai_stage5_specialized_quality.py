from legal_bot import ai


def test_draft_guard_flags_unknown_source_markers_without_touching_valid_ones():
    result = ai._guard_draft_source_markers(
        'استناد معتبر [S1] و ارجاع ساختگی [S4].', {'1', '2'}
    )
    assert '[S1]' in result
    assert '[ارجاع منبع نامعتبر؛ نیازمند بررسی]' in result
    assert '[S4]' not in result
    assert 'کنترل استناد' in result


def test_draft_guard_flags_any_source_marker_when_no_sources_were_supplied():
    result = ai._guard_draft_source_markers('بر اساس قانون [S1]...', set())
    assert '[ارجاع منبع نامعتبر؛ نیازمند بررسی]' in result
    assert 'کنترل استناد' in result


def test_draft_brief_uses_source_guard_and_strengthened_prompt(monkeypatch):
    monkeypatch.setattr(ai, 'AI_ENABLED', True)
    monkeypatch.setattr(ai, 'DEEPSEEK_API_KEY', 'test-key')
    monkeypatch.setattr(ai, 'AI_EXTERNAL_DATA_CONSENT', True)
    captured = []

    def fake_call(messages, temperature=0.05):
        captured.append(messages[-1]['content'])
        return 'دفاع مستند [S1] و ارجاع غیرموجود [S2].'

    monkeypatch.setattr(ai, '_call', fake_call)
    result = ai.draft_legal_brief(
        'واقعیت ارائه‌شده از سوی وکیل', 'لایحه دفاعیه', 'بدوی',
        sources=[{'title': 'قانون نمونه', 'text': 'متن منبع'}],
    )
    assert '[S1]' in result
    assert '[ارجاع منبع نامعتبر؛ نیازمند بررسی]' in result
    assert 'فقط شناسه‌هایی را به‌کار ببر که در فهرست منابع بالا وجود دارند' in captured[0]
    assert 'نبود یک مدرک در ورودی را دلیل نبود آن در پرونده واقعی ندان' in captured[0]
