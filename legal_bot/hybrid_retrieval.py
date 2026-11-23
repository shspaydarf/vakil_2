"""Offline hybrid retrieval for Persian legal case text.

Combines exact normalized token matching, conservative Persian suffix handling,
term-frequency weighting and character n-gram similarity for OCR/typing noise.
It is deterministic, dependency-free and never rewrites source text or citations.
This is lexical/fuzzy retrieval, NOT a neural semantic embedding model.
"""
from __future__ import annotations

import math
import re
from collections import Counter

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_STOP = {
    "از", "به", "با", "در", "را", "که", "و", "یا", "برای", "این", "آن", "یک",
    "چه", "چرا", "چگونه", "است", "هست", "شد", "شود", "می", "من", "ما", "شما",
    "پرونده", "سند", "اسناد", "لطفا", "لطفاً", "بررسی", "کن", "کنید", "درباره",
    "مورد", "آیا", "اگر", "هم", "تا", "اما", "پس", "طبق", "های", "ها",
}
# Only grammatical suffixes are stripped. Legally distinct concepts are never
# treated as synonyms (e.g. فسخ and انفساخ remain separate terms).
_SUFFIXES = ("ترین", "تر", "هایی", "های", "هایِ", "گان", "ان", "ات", "ها", "ی")


def normalize(value: object) -> str:
    text = str(value or "").translate(_DIGITS)
    text = text.replace("ي", "ی").replace("ى", "ی").replace("ك", "ک")
    text = text.replace("ۀ", "ه").replace("ة", "ه").replace("ؤ", "و")
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ٱ", "ا")
    text = re.sub(r"[\u064b-\u065f\u0670\u06d6-\u06ed]", "", text)
    text = text.replace("\u200c", " ").replace("\u200d", " ")
    text = re.sub(r"[^\w\u0600-\u06ff]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def _stem(token: str) -> str:
    for suffix in _SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            return token[:-len(suffix)]
    return token


def terms(value: object) -> list[str]:
    raw = normalize(value).split()
    result = []
    for token in raw:
        token = _stem(token)
        if len(token) > 1 and token not in _STOP:
            result.append(token)
    return result


def _ngrams(token: str, n: int = 3) -> set[str]:
    if len(token) < n:
        return {token} if token else set()
    return {token[i:i+n] for i in range(len(token)-n+1)}


def _dice(a: str, b: str) -> float:
    aa, bb = _ngrams(a), _ngrams(b)
    if not aa or not bb:
        return 0.0
    return 2.0 * len(aa & bb) / (len(aa) + len(bb))


def score_text(question: object, document: object) -> dict[str, float]:
    """Return a stable 0..1 score with interpretable lexical/fuzzy components."""
    q = terms(question)
    d = terms(document)
    if not q or not d:
        return {"score": 0.0, "lexical": 0.0, "fuzzy": 0.0}
    q_counts, d_counts = Counter(q), Counter(d)
    unique_q = list(q_counts)
    # Query coverage, weighted toward rarer terms within this candidate.
    covered = 0.0
    total_weight = 0.0
    fuzzy_total = 0.0
    for term in unique_q:
        weight = 1.0 + math.log1p(len(q) / (1 + d_counts.get(term, 0)))
        total_weight += weight
        if d_counts.get(term, 0):
            covered += weight
        else:
            # Fuzzy matching is deliberately conservative to reduce false
            # positives on short legal terms and article numbers.
            best = max((_dice(term, candidate) for candidate in set(d)), default=0.0)
            if len(term) >= 4 and best >= 0.58:
                fuzzy_total += weight * best
    lexical = covered / total_weight if total_weight else 0.0
    fuzzy = fuzzy_total / total_weight if total_weight else 0.0
    # Exact matching dominates. Fuzzy matching can recover OCR variants but
    # cannot outweigh a complete lack of exact query coverage by itself.
    score = min(1.0, lexical * 0.82 + fuzzy * 0.18)
    return {"score": round(score, 6), "lexical": round(lexical, 6), "fuzzy": round(fuzzy, 6)}


def rank_texts(question: object, texts: list[object]) -> list[tuple[float, int, dict[str, float]]]:
    ranked = []
    for index, text in enumerate(texts):
        parts = score_text(question, text)
        ranked.append((parts["score"], index, parts))
    return sorted(ranked, key=lambda row: (-row[0], row[1]))
