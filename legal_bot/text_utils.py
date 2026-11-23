"""Small shared text helpers used by deterministic legal engines."""
from __future__ import annotations

import re
from typing import Any, Callable, Iterable


def clean_whitespace(value: Any) -> str:
    """Collapse whitespace and convert falsey values to an empty string."""
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_persian_text(value: Any) -> str:
    """Apply the shared Persian character and case normalization."""
    return clean_whitespace(value).replace("ي", "ی").replace("ك", "ک").lower()


def has_any_normalized_term(text: str, *terms: str, normalizer: Callable[[Any], str]) -> bool:
    """Return whether any normalized term occurs in already-normalized text."""
    return any(normalizer(term) in text for term in terms)


def find_law_source_hits(terms, limit=10, *, corpus_loader, normalizer):
    """Find law titles matching any term, preserving the tree engines' result shape."""
    found = []
    for title, articles in corpus_loader().get("laws", {}).items():
        hay = normalizer(title)
        if any(normalizer(term) in hay or hay in normalizer(term) for term in terms):
            found.append({"type": "law", "title": title, "articles": len(articles) if isinstance(articles, list) else None})
            if len(found) >= limit:
                break
    return found
