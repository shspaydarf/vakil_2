"""Deterministic, query-focused context selection for case AI requests.

This module never summarizes or rewrites legal facts. It only ranks existing
source-backed records/pages against the lawyer's explicit question and reports
when coverage is partial. If lexical matching is weak, callers retain the
legacy balanced sample instead of silently narrowing context.
"""
from __future__ import annotations
import json
import re

from .hybrid_retrieval import normalize as hybrid_normalize, terms as hybrid_terms, score_text as hybrid_score_text

_PERSIAN_STOP = {
    'از','به','با','در','را','که','و','یا','برای','این','آن','یک','چه','چرا','چگونه',
    'است','هست','شد','شود','می','من','ما','شما','پرونده','سند','اسناد','لطفا','لطفاً',
    'بررسی','کن','کنید','درباره','مورد','آیا','اگر','هم','تا','اما','پس','طبق'
}
_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')


def _norm(value):
    value = str(value or '').translate(_DIGITS).replace('ي','ی').replace('ك','ک')
    value = re.sub(r'[^\w\u0600-\u06FF]+', ' ', value.lower())
    return value


def query_terms(question):
    return {w for w in _norm(question).split() if len(w) > 1 and w not in _PERSIAN_STOP}


def _record_text(value):
    if isinstance(value, dict):
        return ' '.join(_record_text(v) for k, v in value.items() if k not in {'source_pages','page','document_id','id'})
    if isinstance(value, (list, tuple)):
        return ' '.join(_record_text(v) for v in value)
    return str(value or '')


def relevance_score(value, terms):
    if not terms:
        return 0
    question = " ".join(sorted(terms))
    return hybrid_score_text(question, _record_text(value))["score"]


def select_records(records, question, *, max_items=12, char_budget=1800):
    """Select complete records, preserving their original order in final output."""
    rows = [r for r in (records or []) if isinstance(r, (dict, str, int, float))]
    terms = query_terms(question)
    scored = [(relevance_score(row, terms), idx, row) for idx, row in enumerate(rows)]
    hits = [x for x in scored if x[0] >= 0.12]
    strategy = 'question_relevance' if hits else 'safe_fallback'
    candidates = sorted(hits, key=lambda x: (-x[0], x[1])) if hits else scored
    chosen = []
    used = 0
    for score, idx, row in candidates:
        if len(chosen) >= max(1, int(max_items)):
            break
        encoded = json.dumps(row, ensure_ascii=False, separators=(',', ':'))
        cost = len(encoded) + (1 if chosen else 0)
        if chosen and used + cost > max(1, int(char_budget)):
            continue
        if not chosen and cost > max(1, int(char_budget)):
            # Do not slice a record: skip it rather than corrupt provenance/JSON.
            continue
        chosen.append((idx, row)); used += cost
    chosen.sort(key=lambda x: x[0])
    return [row for _, row in chosen], {'strategy': strategy, 'available': len(rows), 'selected': len(chosen), 'matched': len(hits), 'retrieval': 'offline_hybrid_lexical_fuzzy', 'minimum_score': 0.12}


def select_document_pages(text, question, *, max_pages=6):
    """Return whole page-labelled blocks ranked by query; no text is rewritten."""
    text = str(text or '')
    blocks = [b.strip() for b in re.split(r'(?=\[صفحه\s+\d+\])', text) if b.strip()]
    if len(blocks) < 2:
        return text, {'strategy': 'balanced_sample', 'selected_pages': [], 'available_pages': len(blocks)}
    terms = query_terms(question)
    scored = [(relevance_score(block, terms), i, block) for i, block in enumerate(blocks)]
    hits = [x for x in scored if x[0] >= 0.12]
    if not hits:
        return text, {'strategy': 'balanced_sample', 'selected_pages': [], 'available_pages': len(blocks)}
    selected = sorted(sorted(hits, key=lambda x: (-x[0], x[1]))[:max(1, int(max_pages))], key=lambda x: x[1])
    pages = []
    for _, _, block in selected:
        m = re.match(r'\[صفحه\s+(\d+)\]', block)
        if m:
            pages.append(int(m.group(1)))
    return '\n\n'.join(x[2] for x in selected), {
        'strategy': 'question_relevance_pages', 'selected_pages': pages,
        'available_pages': len(blocks), 'matched_pages': len(hits),
        'retrieval': 'offline_hybrid_lexical_fuzzy', 'minimum_score': 0.12,
    }
