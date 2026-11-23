from pathlib import Path
import ast


def test_ai_case_summary_is_single_bounded_text_only_call(monkeypatch):
    from legal_bot import ai

    monkeypatch.setattr(ai, 'AI_ENABLED', True)
    monkeypatch.setattr(ai, 'DEEPSEEK_API_KEY', 'test-key')
    monkeypatch.setattr(ai, 'AI_EXTERNAL_DATA_CONSENT', True)
    monkeypatch.setattr(ai, 'AI_TEXT_MAX_CHARS', 5000)
    calls = []

    def fake_call(messages, temperature=0.05):
        calls.append((messages, temperature))
        return '📄 خلاصه پرونده\n۱) موضوع: نمونه\n۶) ابهام‌ها: مشخص نیست'

    monkeypatch.setattr(ai, '_call', fake_call)
    source = '[صفحه 1]\n' + ('متن حقوقی نمونه. ' * 1000) + '\n[صفحه 2]\nپاراگراف پایانی'
    result = ai.summarize_case_for_lawyer(source, 'طرفین: الف و ب')

    assert len(calls) == 1
    assert result.startswith('📄 خلاصه پرونده')
    prompt = calls[0][0][1]['content']
    assert 'هیچ واقعیت، نام، تاریخ، مبلغ، ادعا، ماده قانونی یا شماره رأی نساز' in prompt
    assert 'طرفین: الف و ب' in prompt
    assert 'بخش‌هایی از متن برای کنترل هزینه ارسال نشده‌اند' in prompt
    assert 'متن استخراج‌شده پرونده' in prompt
    assert '⚠️ یادداشت پوشش' in result
    assert len(prompt) < 9000


def test_ai_case_summary_requires_external_data_consent(monkeypatch):
    from legal_bot import ai

    monkeypatch.setattr(ai, 'AI_ENABLED', True)
    monkeypatch.setattr(ai, 'DEEPSEEK_API_KEY', 'test-key')
    monkeypatch.setattr(ai, 'AI_EXTERNAL_DATA_CONSENT', False)
    def forbidden_call(*args, **kwargs):
        raise AssertionError('external API must not be called without consent')
    monkeypatch.setattr(ai, '_call', forbidden_call)
    try:
        ai.summarize_case_for_lawyer('[صفحه 1]\nمتن نمونه')
    except RuntimeError as exc:
        assert 'consent' in str(exc)
    else:
        raise AssertionError('expected consent gate')


def test_document_feature_now_runs_analysis_instead_of_placeholder():
    source = Path('legal_bot/handlers.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    node = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'ai_case_feature_select_cb')
    body = ast.get_source_segment(source, node)
    assert "if feature == 'documents'" in body
    assert 'get_case_text(q.from_user.id, cid)' in body
    assert 'await asyncio.to_thread(analyze, extracted_text)' in body
    assert 'summarize_case_for_lawyer' in body
    assert 'entitlement.refund(q.from_user.id, reservation)' in body
