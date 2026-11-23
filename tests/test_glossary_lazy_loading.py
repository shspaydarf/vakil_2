import json

import pytest

from legal_bot import glossary


def _reset_glossary(monkeypatch, path):
    monkeypatch.setattr(glossary, 'GLOSSARY_FILE', path)
    monkeypatch.setattr(glossary, '_loaded', False)
    glossary.RAW_GLOSSARY.clear()
    glossary.INDEX.clear()


def test_glossary_is_not_loaded_until_first_nonempty_query(monkeypatch, tmp_path):
    missing = tmp_path / 'missing-glossary.json'
    _reset_glossary(monkeypatch, missing)

    assert glossary.expand_query('') == []
    assert glossary.lookup('') == []
    assert glossary._loaded is False


def test_missing_glossary_fails_only_when_glossary_feature_is_used(monkeypatch, tmp_path):
    missing = tmp_path / 'missing-glossary.json'
    _reset_glossary(monkeypatch, missing)

    with pytest.raises(FileNotFoundError):
        glossary.expand_query('دادخواست')
    assert glossary._loaded is False


def test_glossary_loads_and_normalizes_once_on_first_use(monkeypatch, tmp_path):
    path = tmp_path / 'glossary.json'
    path.write_text(json.dumps([
        {
            'term': 'دادخواست',
            'aliases': ['درخواست قضایی', 'دادخواست'],
            'definition': 'تعریف آزمایشی',
            'source_refs': [],
        },
        None,
        {'term': '', 'aliases': []},
    ], ensure_ascii=False), encoding='utf-8')
    _reset_glossary(monkeypatch, path)

    assert 'درخواست قضائی' in glossary.expand_query('تنظیم دادخواست')
    assert glossary._loaded is True
    assert len(glossary.INDEX) == 1
    assert glossary.lookup('دادخواست')[0]['term'] == 'دادخواست'


def test_glossary_rejects_non_array_json(monkeypatch, tmp_path):
    path = tmp_path / 'glossary.json'
    path.write_text('{"term": "دادخواست"}', encoding='utf-8')
    _reset_glossary(monkeypatch, path)

    with pytest.raises(ValueError, match='JSON array'):
        glossary.lookup('دادخواست')
