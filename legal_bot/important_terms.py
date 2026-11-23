"""Lazy-loaded high-signal phrase index used by document analysis."""

import json
from pathlib import Path
from threading import Lock

from .files import clean_fa

IMPORTANT_TERMS_FILE = Path(__file__).parent / 'data' / 'iran' / 'important_terms.json'
RAW_IMPORTANT_TERMS = []
INDEX = []
BY_USE = {}
_loaded = False
_load_lock = Lock()


def _ensure_loaded():
    """Load the optional phrase dataset only when analysis needs it."""
    global _loaded
    if _loaded:
        return

    with _load_lock:
        if _loaded:
            return
        with open(IMPORTANT_TERMS_FILE, encoding='utf-8') as source:
            raw_terms = json.load(source)
        if not isinstance(raw_terms, list):
            raise ValueError('Important terms data must contain a JSON array')

        index = []
        by_use = {}
        for item in raw_terms:
            if not isinstance(item, dict):
                continue
            phrase = clean_fa(item.get('phrase', '')).strip()
            if not phrase:
                continue
            uses = list(dict.fromkeys(
                clean_fa(value).strip()
                for value in item.get('uses', [])
                if str(value).strip()
            ))
            entry = {
                'phrase': phrase,
                'category': clean_fa(item.get('category', '')).strip(),
                'uses': uses,
                'priority': int(item.get('priority', 1) or 1),
            }
            index.append(entry)
            for use in uses:
                by_use.setdefault(use, []).append(phrase)

        RAW_IMPORTANT_TERMS.clear()
        RAW_IMPORTANT_TERMS.extend(raw_terms)
        INDEX.clear()
        INDEX.extend(index)
        BY_USE.clear()
        BY_USE.update(by_use)
        _loaded = True


def phrases_for(use=None):
    _ensure_loaded()
    if use:
        return list(BY_USE.get(use, []))
    return [item['phrase'] for item in INDEX]


def matching_phrases(text, use=None, limit=80):
    _ensure_loaded()
    normalized_text = clean_fa(str(text or '')).replace('\u200c', ' ')
    pool = BY_USE.get(use, []) if use else [item['phrase'] for item in INDEX]
    # Prefer multi-word/high-information phrases over short generic words.
    # This prevents generic terms crowding out more useful legal phrases.
    pool = sorted(
        dict.fromkeys(pool),
        key=lambda value: (-len(value.replace('\u200c', ' ')), value),
    )
    hits = []
    seen = set()
    for phrase in pool:
        candidate = phrase.replace('\u200c', ' ')
        if candidate and candidate in normalized_text and phrase not in seen:
            seen.add(phrase)
            hits.append(phrase)
            if len(hits) >= limit:
                break
    return hits


def category_counts():
    _ensure_loaded()
    counts = {}
    for item in INDEX:
        category = item['category']
        counts[category] = counts.get(category, 0) + 1
    return counts
