import json

import pytest

from legal_bot import important_terms


def _reset(monkeypatch, path):
    monkeypatch.setattr(important_terms, 'IMPORTANT_TERMS_FILE', path)
    monkeypatch.setattr(important_terms, '_loaded', False)
    important_terms.RAW_IMPORTANT_TERMS.clear()
    important_terms.INDEX.clear()
    important_terms.BY_USE.clear()


def test_import_does_not_read_missing_data_until_feature_is_used(monkeypatch, tmp_path):
    missing = tmp_path / 'missing.json'
    _reset(monkeypatch, missing)
    assert important_terms.phrases_for is not None
    with pytest.raises(FileNotFoundError):
        important_terms.phrases_for()


def test_phrase_index_loads_on_first_use_and_is_reused(monkeypatch, tmp_path):
    path = tmp_path / 'important_terms.json'
    path.write_text(json.dumps([
        {'phrase': 'وجه التزام', 'category': 'قرارداد', 'uses': ['contract'], 'priority': 3},
        {'phrase': '', 'category': 'ignored', 'uses': []},
        None,
    ], ensure_ascii=False), encoding='utf-8')
    _reset(monkeypatch, path)

    assert important_terms.matching_phrases('شرط وجه التزام مهم') == ['وجه التزام']
    assert important_terms.phrases_for('contract') == ['وجه التزام']
    assert important_terms.category_counts() == {'قرارداد': 1}
    assert important_terms._loaded is True


def test_phrase_index_rejects_non_array_json(monkeypatch, tmp_path):
    path = tmp_path / 'important_terms.json'
    path.write_text('{"phrase": "وجه التزام"}', encoding='utf-8')
    _reset(monkeypatch, path)
    with pytest.raises(ValueError, match='JSON array'):
        important_terms.category_counts()
