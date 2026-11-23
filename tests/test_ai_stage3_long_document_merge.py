from legal_bot import ai


def test_structured_analysis_keeps_all_successful_chunks_when_synthesis_fails(monkeypatch):
    monkeypatch.setattr(ai, 'AI_ENABLED', True)
    monkeypatch.setattr(ai, 'DEEPSEEK_API_KEY', 'test-key')
    monkeypatch.setattr(ai, 'AI_EXTERNAL_DATA_CONSENT', True)
    monkeypatch.setattr(ai, 'AI_MAX_CHARS', 1000)
    calls = []
    monkeypatch.setattr(ai, '_chunks', lambda text: ([f'[صفحه {i}]\nمتن صفحه {i}' for i in range(1, 9)] + [f'[صفحه {i}]\nمتن صفحه {i}' for i in range(14, 22)], True))

    def fake_call(messages, temperature=0.05):
        calls.append(messages)
        prompt = messages[-1]['content']
        if 'بخش ' in prompt and 'از ' in prompt:
            import re
            m = re.search(r'\[صفحه (\d+)\]', prompt)
            page = int(m.group(1))
            return '{"key_facts":[{"fact":"واقعیت صفحه %s","source_pages":[%s]}]}' % (page, page)
        raise RuntimeError('simulated synthesis outage')

    monkeypatch.setattr(ai, '_call', fake_call)
    source = '\n'.join('[صفحه %d]\nمتن سند صفحه %d. ' % (i, i) + ('الف' * 9000) for i in range(1, 22))
    result = ai.structured_analysis(source)

    facts = result['key_facts']
    assert len(facts) == 16
    pages = {p for item in facts for p in item['source_pages']}
    assert pages.intersection(range(1, 9)) == set(range(1, 9))
    assert pages.intersection(range(14, 22)) == set(range(14, 22))
    assert result['ai_truncated'] is True
    assert result['ai_chunks_processed'] == 16
    assert result['ai_failed_chunks'] == 0


def test_structured_analysis_does_not_discard_tail_before_chunk_selection(monkeypatch):
    monkeypatch.setattr(ai, 'AI_ENABLED', True)
    monkeypatch.setattr(ai, 'DEEPSEEK_API_KEY', 'test-key')
    monkeypatch.setattr(ai, 'AI_EXTERNAL_DATA_CONSENT', True)
    monkeypatch.setattr(ai, 'AI_MAX_CHARS', 20000)
    chunks_seen = []
    monkeypatch.setattr(ai, '_chunks', lambda text: ([f'[صفحه {i}]\nمتن صفحه {i}' for i in range(1, 9)] + [f'[صفحه {i}]\nمتن صفحه {i}' for i in range(14, 22)], True))

    def fake_call(messages, temperature=0.05):
        prompt = messages[-1]['content']
        if 'بخش ' in prompt and 'از ' in prompt:
            chunks_seen.append(prompt)
            import re
            m = re.search(r'\[صفحه (\d+)\]', prompt)
            page = int(m.group(1))
            return '{"key_facts":[{"fact":"واقعیت صفحه %s","source_pages":[%s]}]}' % (page, page)
        # Return the same complete extracted evidence for the synthesis.
        import json
        facts = []
        for prompt in chunks_seen:
            import re
            page = int(re.search(r'\[صفحه (\d+)\]', prompt).group(1))
            facts.append({'fact': 'واقعیت صفحه %s' % page, 'source_pages': [page]})
        return json.dumps({'key_facts': facts}, ensure_ascii=False)

    monkeypatch.setattr(ai, '_call', fake_call)
    source = '\n'.join('[صفحه %d]\nمتن سند صفحه %d. ' % (i, i) + ('الف' * 9000) for i in range(1, 22))
    result = ai.structured_analysis(source)
    pages = {p for item in result['key_facts'] for p in item['source_pages']}
    assert 21 in pages
    assert 1 in pages
    assert result['ai_truncated'] is True
