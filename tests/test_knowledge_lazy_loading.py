import json

import pytest

from legal_bot import knowledge


def _reset(monkeypatch, path):
    monkeypatch.setattr(knowledge, 'ROOT', path.parent)
    monkeypatch.setattr(knowledge, '_loaded', False)
    knowledge.REGISTRY.clear()
    knowledge.AUTHORITY_BY_ID.clear()
    knowledge.LAW_BY_TITLE.clear()


def test_registry_file_is_required_only_when_registry_lookup_is_used(monkeypatch, tmp_path):
    missing = tmp_path / 'official_sources.json'
    _reset(monkeypatch, missing)
    with pytest.raises(FileNotFoundError):
        knowledge.law_source('قانون نمونه')


def test_registry_loads_once_and_builds_lookup_indexes(monkeypatch, tmp_path):
    path = tmp_path / 'official_sources.json'
    path.write_text(json.dumps({
        'authorities': [{'id': 'majles', 'name': 'مجلس'}],
        'laws': [{
            'title': 'قانون نمونه', 'status': 'verified',
            'primary_sources': ['majles'], 'known_source_urls': [],
        }],
    }, ensure_ascii=False), encoding='utf-8')
    _reset(monkeypatch, path)

    assert knowledge.is_text_verified('قانون نمونه') is True
    assert knowledge.law_source('قانون نمونه')['primary_sources'] == ['مجلس']
    assert knowledge.verification_label('قانون نمونه') == 'منبع و متن تأییدشده'
    assert knowledge._loaded is True


def test_registry_rejects_non_object_json(monkeypatch, tmp_path):
    path = tmp_path / 'official_sources.json'
    path.write_text('[]', encoding='utf-8')
    _reset(monkeypatch, path)
    with pytest.raises(ValueError, match='JSON object'):
        knowledge.law_source('قانون نمونه')
