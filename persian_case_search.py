# -*- coding: utf-8 -*-
"""Fast, Persian-aware local search over full extracted case text.

The source text is never replaced. A normalized shadow representation is used
only for matching, while returned snippets are taken from the original text.
"""

import re
from typing import List, Dict, Iterable, Tuple

ARABIC_TO_PERSIAN = str.maketrans({
    "ي": "ی", "ى": "ی", "ك": "ک", "ۀ": "هٔ", "ة": "ه",
    "ؤ": "و", "إ": "ا", "أ": "ا", "ٱ": "ا",
})

DIACRITICS_RE = re.compile(r"[\u064B-\u065F\u0670\u06D6-\u06ED]")
SPACE_RE = re.compile(r"\s+")


def normalize_fa(text: str) -> str:
    """Normalize common Persian/Arabic typing differences for matching only."""
    if not text:
        return ""
    text = str(text).translate(ARABIC_TO_PERSIAN)
    text = DIACRITICS_RE.sub("", text)
    text = text.replace("\u200c", " ")       # ZWNJ → searchable space
    text = text.replace("\u200d", " ")
    text = text.replace("\u200e", "")
    text = text.replace("\u200f", "")
    text = text.replace("\u0640", "")        # tatweel
    text = SPACE_RE.sub(" ", text)
    return text.strip()


def compact_fa(text: str) -> str:
    """A second representation that ignores spaces/ZWNJ between words."""
    return normalize_fa(text).replace(" ", "")


def query_variants(query: str) -> List[str]:
    """Generate a small, deterministic set of useful Persian variants."""
    q = normalize_fa(query)
    if not q:
        return []
    variants = [q]

    # Space/ZWNJ variants for multi-word searches.
    if " " in q:
        variants.append(q.replace(" ", "\u200c"))
        variants.append(q.replace(" ", ""))
    elif len(q) >= 5:
        # For a long single token, compact form is useful when OCR glued text.
        variants.append(q.replace(" ", ""))

    # Avoid duplicate variants.
    out = []
    seen = set()
    for v in variants:
        v = normalize_fa(v)
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _line_spans(text: str) -> List[Tuple[int, int, str]]:
    spans = []
    pos = 0
    for line in text.splitlines(True):
        raw = line.rstrip("\r\n")
        spans.append((pos, pos + len(raw), raw))
        pos += len(line)
    if not spans and text:
        spans.append((0, len(text), text))
    return spans


def _page_lines(page_text: str) -> List[str]:
    return page_text.splitlines() or ([page_text] if page_text else [])


def search_pages(pages: Iterable[Tuple[int, str]], query: str,
                 max_results: int = 20, context_before: int = 2,
                 context_after: int = 2) -> List[Dict]:
    """Search full extracted page text and return numbered contextual matches.

    pages: iterable of (real_page_number, full_extracted_page_text)
    """
    variants = query_variants(query)
    if not variants:
        return []

    results = []
    seen = set()

    for page_no, page_text in pages:
        lines = _page_lines(page_text)
        normalized_lines = [normalize_fa(x) for x in lines]
        compact_lines = [compact_fa(x) for x in lines]

        for i, (nline, cline) in enumerate(zip(normalized_lines, compact_lines)):
            matched = False
            for v in variants:
                nv = normalize_fa(v)
                if nv and (nv in nline or compact_fa(nline).find(compact_fa(nv)) >= 0):
                    matched = True
                    break
            if not matched:
                continue

            # Deduplicate adjacent/overlapping variant matches on the same line.
            key = (page_no, i)
            if key in seen:
                continue
            seen.add(key)

            lo = max(0, i - context_before)
            hi = min(len(lines), i + context_after + 1)
            snippet_lines = [x.strip() for x in lines[lo:hi] if x.strip()]
            results.append({
                "page": page_no,
                "line": i + 1,
                "snippet": "\n".join(snippet_lines),
                "matched_line": lines[i].strip(),
            })
            if len(results) >= max_results:
                return results

    return results


def search_text_with_pages(text: str, query: str, max_results: int = 20) -> List[Dict]:
    """Fallback for legacy records that contain one text blob.

    Page markers such as '--- PAGE 3 ---' are recognized when present.
    """
    if not text:
        return []

    page_re = re.compile(
        r"(?im)^\s*(?:\[\s*)?(?:page|صفحه)\s+(\d+)\s*(?:\]\s*|---\s*)?$"
    )
    matches = list(page_re.finditer(text))
    if not matches:
        return search_pages([(1, text)], query, max_results=max_results)

    pages = []
    for idx, m in enumerate(matches):
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        pages.append((int(m.group(1)), text[start:end]))
    return search_pages(pages, query, max_results=max_results)
