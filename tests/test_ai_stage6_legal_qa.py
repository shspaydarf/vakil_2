from legal_bot import ai


def test_legal_qa_prompt_requires_jurisdiction_clarification(monkeypatch):
    monkeypatch.setattr(ai, '_call', lambda messages, temperature=0.05: messages[0]['content'])
    result = ai.ask_ai_question('آیا این کار قانونی است؟')
    assert 'حوزه قضایی' in result
    assert 'قانون کشور خاصی را فرض نکن' in result
    assert 'مهم‌ترین سؤال تکمیلی' in result


def test_legal_qa_prompt_guards_against_fake_or_unsupported_citations(monkeypatch):
    monkeypatch.setattr(ai, '_call', lambda messages, temperature=0.05: messages[0]['content'])
    result = ai.ask_ai_question('طبق ماده ۱۲ چه می‌شود؟')
    assert 'هیچ ماده قانونی، شماره رأی' in result
    assert 'منبع قابل اتکا در ورودی موجود باشد' in result
    assert 'به‌روز تأییدشده' in result


def test_legal_qa_does_not_attach_case_context_unless_selected(monkeypatch):
    captured = {}
    def fake_call(messages, temperature=0.05):
        captured['messages'] = messages
        return 'ok'
    monkeypatch.setattr(ai, '_call', fake_call)
    assert ai.ask_ai_question('سؤال عمومی') == 'ok'
    payload = '\n'.join(m['content'] for m in captured['messages'])
    assert 'خلاصه محلی پرونده' not in payload
    assert 'سؤال عمومی' in payload


def test_legal_qa_includes_only_explicitly_selected_case_summary(monkeypatch):
    captured = {}
    def fake_call(messages, temperature=0.05):
        captured['messages'] = messages
        return 'ok'
    monkeypatch.setattr(ai, '_call', fake_call)
    ai.ask_ai_question('سؤال درباره پرونده', case_summary='خلاصه انتخاب‌شده', standard_prompt='دستور انتخاب‌شده')
    payload = '\n'.join(m['content'] for m in captured['messages'])
    assert 'خلاصه انتخاب‌شده' in payload
    assert 'دستور انتخاب‌شده' in payload


def test_legal_qa_adds_local_sources_only_when_iran_scope_is_explicit(monkeypatch):
    captured = {}
    monkeypatch.setattr(ai, '_call', lambda messages, temperature=0.05: captured.setdefault('payload', '\n'.join(m['content'] for m in messages)) or 'ok')
    monkeypatch.setattr('legal_bot.laws.search_legal_research', lambda q, limit=5: [{
        'law': 'قانون نمونه', 'article': '۱۲', 'clean_text': 'متن موجود برای آزمون',
        'citation': {'verification_label': 'وضعیت منبع نامشخص', 'source_urls': []}
    }])
    ai.ask_ai_question('طبق قانون ایران، ماده ۱۲ چه می‌گوید؟')
    assert 'نتایج بازیابی محلی' in captured['payload']
    assert 'متن موجود برای آزمون' in captured['payload']
    assert 'جاری بودن منبع نیست' in captured['payload']


def test_legal_qa_does_not_retrieve_local_iran_sources_for_unspecified_jurisdiction(monkeypatch):
    called = {'value': False}
    def fake_search(*args, **kwargs):
        called['value'] = True
        return []
    monkeypatch.setattr('legal_bot.laws.search_legal_research', fake_search)
    monkeypatch.setattr(ai, '_call', lambda messages, temperature=0.05: 'ok')
    assert ai.ask_ai_question('آیا این قرارداد معتبر است؟') == 'ok'
    assert called['value'] is False


def test_case_ai_external_call_is_blocked_without_external_data_consent(monkeypatch):
    monkeypatch.setattr(ai, 'AI_ENABLED', True)
    monkeypatch.setattr(ai, 'DEEPSEEK_API_KEY', 'test-key')
    monkeypatch.setattr(ai, 'AI_EXTERNAL_DATA_CONSENT', False)

    def forbidden_request(*args, **kwargs):
        raise AssertionError('external provider request must not be sent without consent')

    monkeypatch.setattr(ai.requests, 'post', forbidden_request)
    try:
        ai.ask_ai_question('سؤال پرونده', case_summary='متن محرمانه پرونده')
    except RuntimeError as exc:
        assert 'consent' in str(exc)
    else:
        raise AssertionError('expected external-consent gate')
