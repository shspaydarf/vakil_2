from pathlib import Path
import ast


def test_ai_case_review_is_single_bounded_text_only_call(monkeypatch):
    from legal_bot import ai
    monkeypatch.setattr(ai, 'AI_ENABLED', True)
    monkeypatch.setattr(ai, 'DEEPSEEK_API_KEY', 'test-key')
    monkeypatch.setattr(ai, 'AI_EXTERNAL_DATA_CONSENT', True)
    monkeypatch.setattr(ai, 'AI_TEXT_MAX_CHARS', 5000)
    calls = []

    def fake_call(messages, temperature=0.05):
        calls.append((messages, temperature))
        return 'مورد نیازمند بررسی: دو عبارت زیر درباره پرداخت متفاوت‌اند.'

    monkeypatch.setattr(ai, '_call', fake_call)
    source = '[صفحه 1]\nپرداخت انجام شد.\n' + ('متن نمونه حقوقی. ' * 900) + '\n[صفحه 4]\nپرداخت انجام نشده است.'
    result = ai.review_case_contradictions(source, 'بررسی محلی: دو عبارت پرداخت متفاوت‌اند')
    assert len(calls) == 1
    assert calls[0][1] == 0.0
    prompt = calls[0][0][1]['content']
    assert 'هیچ واقعیت، تاریخ، مبلغ، نام، شماره صفحه یا استناد نساز' in prompt
    assert 'متن استخراج‌شده پرونده' in prompt
    assert 'بررسی محلی' in prompt
    assert len(prompt) < 9000
    assert result.startswith('🔎 بررسی تکمیلی ایرادها و تناقض‌ها')
    assert '⚖️ موارد گزارش‌شده سرنخ بررسی هستند' in result
    assert 'یادداشت پوشش' in result


def test_ai_case_review_requires_external_data_consent(monkeypatch):
    from legal_bot import ai
    monkeypatch.setattr(ai, 'AI_ENABLED', True)
    monkeypatch.setattr(ai, 'DEEPSEEK_API_KEY', 'test-key')
    monkeypatch.setattr(ai, 'AI_EXTERNAL_DATA_CONSENT', False)
    monkeypatch.setattr(ai, '_call', lambda *a, **k: (_ for _ in ()).throw(AssertionError('API called')))
    try:
        ai.review_case_contradictions('متن نمونه')
    except RuntimeError as exc:
        assert 'consent' in str(exc)
    else:
        raise AssertionError('expected consent gate')


def test_review_feature_is_connected_to_case_text_and_local_scan():
    source = Path('legal_bot/handlers.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    node = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'ai_case_feature_select_cb')
    body = ast.get_source_segment(source, node)
    assert "if feature == 'review'" in body
    assert 'get_case_text(q.from_user.id, cid)' in body
    assert 'brief_consistency_check' in body
    assert 'review_case_contradictions' in body
    assert 'entitlement.refund(q.from_user.id, reservation)' in body


def test_local_review_reports_explicit_payment_conflict_without_claiming_truth():
    from legal_bot.brief_workspace import brief_consistency_check, format_consistency_report
    text = '[صفحه 1]\nوجه پرداخت شد.\n[صفحه 2]\nوجه پرداخت نشده است.'
    report = brief_consistency_check('', case_text=text)
    assert report['count'] >= 1
    rendered = format_consistency_report(report)
    assert 'پرداخت' in rendered
    assert 'درباره درست یا نادرست بودن هیچ‌یک تصمیم نمی‌گیرد' in rendered


def test_ai_case_review_discards_findings_with_unverifiable_quotes(monkeypatch):
    import json
    from legal_bot import ai
    monkeypatch.setattr(ai, 'AI_ENABLED', True)
    monkeypatch.setattr(ai, 'DEEPSEEK_API_KEY', 'test-key')
    monkeypatch.setattr(ai, 'AI_EXTERNAL_DATA_CONSENT', True)
    monkeypatch.setattr(ai, 'AI_TEXT_MAX_CHARS', 12000)
    monkeypatch.setattr(ai, '_call', lambda *a, **k: json.dumps({'findings': [
        {'topic': 'تعارض پرداخت', 'type': 'تناقض احتمالی', 'quote1': 'پرداخت انجام شد.',
         'quote2': 'پرداخت انجام نشده است.', 'importance': 'زیاد', 'action': 'اصل رسید بررسی شود'},
        {'topic': 'شاهد ساختگی', 'type': 'تناقض احتمالی', 'quote1': 'این عبارت در متن نیست',
         'quote2': 'پرداخت انجام نشده است.', 'importance': 'زیاد', 'action': 'بررسی شود'}
    ]}, ensure_ascii=False))
    source = '[صفحه 1]\nپرداخت انجام شد.\n[صفحه 2]\nپرداخت انجام نشده است.'
    result = ai.review_case_contradictions(source)
    assert 'تعارض پرداخت' in result
    assert 'شاهد اول (تطبیق‌شده با متن ورودی)' in result
    assert 'شاهد ساختگی' not in result


def test_ai_review_quote_verifier_normalizes_whitespace_and_persian_variants():
    from legal_bot.ai import _validated_review_findings
    source = 'پرداخت   انجام شد.\nمبلغ پرداخت نشده است.'
    payload = {'findings': [{'topic': 'پرداخت', 'type': 'ابهام',
        'quote1': 'پرداخت انجام شد.', 'quote2': 'مبلغ پرداخت نشده است.',
        'importance': 'متوسط', 'action': 'رسید بررسی شود'}]}
    assert len(_validated_review_findings(payload, source)) == 1
