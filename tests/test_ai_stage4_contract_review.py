from legal_bot import ai


def test_contract_review_only_keeps_verifiable_quotes(monkeypatch):
    source = 'طرف اول متعهد است مبلغ را تا روز دهم پرداخت کند. طرف دوم کالا را تا روز بیستم تحویل می‌دهد.'
    monkeypatch.setattr(ai, 'AI_ENABLED', True)
    monkeypatch.setattr(ai, 'DEEPSEEK_API_KEY', 'test-key')
    monkeypatch.setattr(ai, 'AI_EXTERNAL_DATA_CONSENT', True)
    monkeypatch.setattr(ai, '_call', lambda messages, temperature=0.0: '{"findings":['
        '{"topic":"مهلت پرداخت","risk":"متوسط","quote":"طرف اول متعهد است مبلغ را تا روز دهم پرداخت کند.","reason":"مهلت نیازمند تطبیق با شرایط معامله است.","suggestion":"مبدأ محاسبه مهلت روشن شود."},'
        '{"topic":"ساختگی","risk":"زیاد","quote":"طرف اول باید جریمه بدهد.","reason":"ساختگی","suggestion":"ساختگی"}]}')
    result = ai.review_contract_risks(source, 'نمونه')
    assert 'مهلت پرداخت' in result
    assert 'طرف اول متعهد است مبلغ را تا روز دهم پرداخت کند.' in result
    assert 'ساختگی' not in result


def test_contract_review_requires_text_and_consent(monkeypatch):
    monkeypatch.setattr(ai, 'AI_ENABLED', False)
    try:
        ai.review_contract_risks('متن قرارداد')
    except RuntimeError:
        pass
    else:
        raise AssertionError('AI consent/config guard must apply')


def test_contract_review_empty_text_rejected_when_enabled(monkeypatch):
    monkeypatch.setattr(ai, 'AI_ENABLED', True)
    monkeypatch.setattr(ai, 'DEEPSEEK_API_KEY', 'test-key')
    monkeypatch.setattr(ai, 'AI_EXTERNAL_DATA_CONSENT', True)
    try:
        ai.review_contract_risks('   ')
    except ValueError:
        pass
    else:
        raise AssertionError('empty contract text must be rejected')


def test_contract_review_reports_each_playbook_criterion_and_verifies_evidence(monkeypatch):
    source = 'طرف اول متعهد است مبلغ را تا روز دهم پرداخت کند.'
    monkeypatch.setattr(ai, 'AI_ENABLED', True)
    monkeypatch.setattr(ai, 'DEEPSEEK_API_KEY', 'test-key')
    monkeypatch.setattr(ai, 'AI_EXTERNAL_DATA_CONSENT', True)
    monkeypatch.setattr(ai, '_call', lambda messages, temperature=0.0: '{"findings":[{"criterion_id":"payment","topic":"پرداخت","risk":"متوسط","quote":"طرف اول متعهد است مبلغ را تا روز دهم پرداخت کند.","reason":"مهلت پرداخت نیازمند بررسی است.","suggestion":"مبدأ مهلت روشن شود."},{"criterion_id":"payment","topic":"ساختگی","risk":"زیاد","quote":"این نقل قول در قرارداد نیست.","reason":"ساختگی","suggestion":"ساختگی"}]}')
    playbook = {'title': 'نمونه', 'criteria': [{'id': 'payment', 'label': 'مبلغ و پرداخت'}, {'id': 'delivery', 'label': 'تحویل'}]}
    result = ai.review_contract_risks(source, 'نمونه', playbook)
    assert 'مبلغ و پرداخت — دارای یافته' in result
    assert 'تحویل — نیازمند بررسی' in result
    assert 'طرف اول متعهد است مبلغ را تا روز دهم پرداخت کند.' in result
    assert 'این نقل قول در قرارداد نیست' not in result


def test_contract_review_includes_conservative_management_summary(monkeypatch):
    source = 'طرف اول متعهد است مبلغ را تا روز دهم پرداخت کند.'
    monkeypatch.setattr(ai, 'AI_ENABLED', True)
    monkeypatch.setattr(ai, 'DEEPSEEK_API_KEY', 'test-key')
    monkeypatch.setattr(ai, 'AI_EXTERNAL_DATA_CONSENT', True)
    monkeypatch.setattr(ai, '_call', lambda messages, temperature=0.0: '{"findings":[{"criterion_id":"payment","topic":"پرداخت","risk":"زیاد","quote":"طرف اول متعهد است مبلغ را تا روز دهم پرداخت کند.","reason":"مهلت نیازمند بررسی است.","suggestion":"مبدأ مهلت روشن شود."}]}')
    playbook = {
        'title': 'نمونه',
        'criteria': [{'id': 'payment', 'label': 'مبلغ و پرداخت'}, {'id': 'delivery', 'label': 'تحویل'}],
        'follow_up_questions': ['آیا رسید پرداخت موجود است؟'],
    }
    result = ai.review_contract_risks(source, 'نمونه', playbook)
    assert '📌 خلاصه مدیریتی بررسی' in result
    assert 'معیارهای دارای یافته مستند: 1 از 2' in result
    assert 'یافته‌های قابل استناد به متن: 1 (زیاد: 1' in result
    assert 'آیا رسید پرداخت موجود است؟' in result
    assert 'نبود یافته، اثبات رعایت معیار' in result
