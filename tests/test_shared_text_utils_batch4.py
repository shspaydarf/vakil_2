from legal_bot.text_utils import clean_whitespace, has_any_normalized_term


def _norm(value):
    return clean_whitespace(value).replace("ي", "ی").replace("ك", "ک").lower()


def test_clean_whitespace_preserves_existing_engine_semantics():
    assert clean_whitespace(None) == ""
    assert clean_whitespace("  الف\n\tب  ") == "الف ب"
    assert clean_whitespace(0) == ""  # matches the prior local helpers


def test_has_any_normalized_term_uses_supplied_normalizer():
    text = _norm("این متن درباره چک و سفته است")
    assert has_any_normalized_term(text, "چك", "قرارداد", normalizer=_norm)
    assert not has_any_normalized_term(text, "مالکیت", "اجاره", normalizer=_norm)
    assert not has_any_normalized_term(text, normalizer=_norm)


def test_find_law_source_hits_preserves_limit_and_result_shape():
    from legal_bot.text_utils import find_law_source_hits

    corpus = {
        "laws": {
            "قانون مدنی": [{"article": 1}],
            "قانون تجارت": [{"article": 1}, {"article": 2}],
            "قانون کار": "unexpected-shape",
        }
    }
    hits = find_law_source_hits(
        ["قانون"], 2, corpus_loader=lambda: corpus, normalizer=_norm
    )
    assert hits == [
        {"type": "law", "title": "قانون مدنی", "articles": 1},
        {"type": "law", "title": "قانون تجارت", "articles": 2},
    ]


def test_find_law_source_hits_handles_non_list_article_payload():
    from legal_bot.text_utils import find_law_source_hits

    corpus = {"laws": {"قانون کار": "unexpected-shape"}}
    hits = find_law_source_hits(
        ["قانون کار"], corpus_loader=lambda: corpus, normalizer=_norm
    )
    assert hits == [{"type": "law", "title": "قانون کار", "articles": None}]
