from legal_bot import ai


def test_exact_duplicate_paragraphs_removed_only_within_same_page():
    source = (
        '[صفحه 1]\nبند تکراری و یکسان.\n\nبند تکراری و یکسان.\n\nبند دیگر.\n'
        '[صفحه 2]\nبند تکراری و یکسان.'
    )
    compact, removed = ai._dedupe_exact_paragraphs_per_page(source)
    assert removed == 1
    assert compact.count('بند تکراری و یکسان.') == 2
    assert '[صفحه 1]' in compact and '[صفحه 2]' in compact


def test_structured_analysis_uses_one_call_per_chunk_without_synthesis(monkeypatch):
    monkeypatch.setattr(ai, 'AI_ENABLED', True)
    monkeypatch.setattr(ai, 'DEEPSEEK_API_KEY', 'test-key')
    monkeypatch.setattr(ai, 'AI_EXTERNAL_DATA_CONSENT', True)
    monkeypatch.setattr(ai, '_chunks', lambda text: (['[صفحه 1]\nمتن اول', '[صفحه 2]\nمتن دوم'], False))
    calls = []

    def fake_call(messages, temperature=0.05):
        calls.append(messages)
        import re
        page = int(re.search(r'\[صفحه (\d+)\]', messages[-1]['content']).group(1))
        return '{"key_facts":[{"fact":"نکته %s","source_pages":[%s]}]}' % (page, page)

    monkeypatch.setattr(ai, '_call', fake_call)
    result = ai.structured_analysis('[صفحه 1]\nمتن اول\n[صفحه 2]\nمتن دوم')
    assert len(calls) == 2
    assert result['ai_synthesis_calls_saved'] == 1
    assert result['ai_chunks_processed'] == 2
    assert len(result['key_facts']) == 2


def test_local_legal_sources_rank_by_lexical_overlap():
    records = [
        {'law': 'قانون اجاره', 'text': 'موجر مستأجر اجاره‌بها'},
        {'law': 'قانون کار', 'text': 'کارگر کارفرما حقوق'},
    ]
    ranked = ai._rank_local_legal_records(records, 'اختلاف کارگر و کارفرما درباره حقوق', limit=1)
    assert ranked[0]['law'] == 'قانون کار'
