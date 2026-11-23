from legal_bot.ai import _chunks


def test_long_page_chunks_keep_page_marker_and_sentence_boundaries():
    sentences = [f"بند شماره {i} دارای تعهد مشخص است." for i in range(1, 900)]
    source = "[صفحه 7]\n" + " ".join(sentences)
    chunks, truncated = _chunks(source, size=1800, max_chunks=16)
    assert chunks
    assert all(chunk.startswith('[صفحه 7]') for chunk in chunks)
    assert any('بند شماره 1 ' in chunk for chunk in chunks)
    assert any('بند شماره 899 ' in chunk for chunk in chunks)
    assert truncated is True


def test_small_page_text_is_not_split_or_marked_truncated():
    source = '[صفحه 1]\nاین یک سند کوتاه است.\n[صفحه 2]\nاین صفحه دوم است.'
    chunks, truncated = _chunks(source, size=8500, max_chunks=16)
    assert len(chunks) == 1
    assert '[صفحه 1]' in chunks[0] and '[صفحه 2]' in chunks[0]
    assert truncated is False
