"""Lazy-loaded legal glossary helpers.

The glossary is optional for API startup but required for glossary-backed search.
Loading it on first use keeps unrelated bot/API routes available when the data
file is absent, while still failing explicitly when a glossary operation is
requested without its required source data.
"""

import json
from threading import Lock

from .config import GLOSSARY_FILE
from .files import clean_fa

RAW_GLOSSARY = []
INDEX = []
_loaded = False
_load_lock = Lock()


def _build_index(raw_glossary):
    index = []
    for item in raw_glossary:
        if not isinstance(item, dict):
            continue
        term = clean_fa(item.get('term', '')).strip()
        if not term:
            continue
        aliases = [
            clean_fa(value).strip()
            for value in item.get('aliases', [])
            if str(value).strip()
        ]
        index.append({
            'term': term,
            'aliases': list(dict.fromkeys(aliases)),
            'definition': clean_fa(item.get('definition', '')).strip(),
            'note': clean_fa(item.get('note', '')).strip(),
            'category': clean_fa(item.get('category', '')).strip(),
            'source_type': str(item.get('source_type', '')).strip(),
            'source_refs': (
                item.get('source_refs')
                if isinstance(item.get('source_refs'), list)
                else []
            ),
        })
    return index


def _ensure_loaded():
    """Load and normalize the glossary once, on the first glossary request."""
    global _loaded
    if _loaded:
        return

    with _load_lock:
        if _loaded:
            return
        # Do not swallow missing/invalid source data: legal search must not
        # silently continue with an empty glossary.
        with open(GLOSSARY_FILE, encoding='utf-8') as source:
            raw_glossary = json.load(source)
        if not isinstance(raw_glossary, list):
            raise ValueError('Legal glossary must contain a JSON array')

        index = _build_index(raw_glossary)
        RAW_GLOSSARY.clear()
        RAW_GLOSSARY.extend(raw_glossary)
        INDEX.clear()
        INDEX.extend(index)
        _loaded = True


def _norm(value):
    return clean_fa(str(value or '')).replace('\u200c', ' ').lower().strip()


def expand_query(query, limit=12):
    """Expand a local search query with terms and near-synonyms.

    Related terms are search hints, not assertions of legal equivalence.
    """
    q = _norm(query)
    if not q:
        return []
    _ensure_loaded()
    terms = [q]
    for item in INDEX:
        vocab = [item['term'], *item['aliases']]
        if any(_norm(value) and _norm(value) in q for value in vocab):
            terms.extend(vocab)
    return list(dict.fromkeys(terms))[:limit]


def lookup(query, limit=5):
    q = _norm(query)
    if not q:
        return []
    _ensure_loaded()
    scored = []
    for item in INDEX:
        vocab = [item['term'], *item['aliases']]
        score = 0
        for value in vocab:
            normalized = _norm(value)
            if not normalized:
                continue
            if q == normalized:
                score = max(score, 100)
            elif normalized in q:
                score = max(score, 80)
            elif q in normalized:
                score = max(score, 60)
        if score:
            scored.append((score, item))
    scored.sort(key=lambda pair: (-pair[0], pair[1]['term']))
    return [item for _, item in scored[:limit]]


def format_entries(entries):
    lines = []
    for item in entries:
        lines.append(f"⚖️ {item['term']}")
        if item['definition']:
            lines.append(f"تعریف ساده: {item['definition']}")
        if item['aliases']:
            lines.append('مترادف/عبارت‌های نزدیک: ' + '، '.join(item['aliases']))
        if item['note']:
            lines.append(f"نکته: {item['note']}")
        if item.get('source_refs'):
            refs = '؛ '.join(
                f"{ref.get('law', '')} ماده {ref.get('article', '')}"
                for ref in item['source_refs'][:3]
                if isinstance(ref, dict)
            )
            if refs:
                lines.append('منبع درون‌مجموعه: ' + refs)
        lines.append('')
    return '\n'.join(lines).strip()
