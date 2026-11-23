"""V167.1 conservative source/PDF text segmentation.

This layer operates between PDF/OCR extraction and analysis.  It removes only
high-signal page artifacts (repeated headers/footers, standalone page numbers,
URLs and known training notices) and preserves page boundaries.  It does not
invent or rewrite legal facts.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Iterable, Tuple

from .source_quality import is_probable_source_noise

_PAGE_MARKER = re.compile(r"^\s*\[صفحه\s+[0-9۰-۹]+\]\s*$")
_STANDALONE_ARTIFACTS = re.compile(
    r"^\s*(?:صفحه\s*[0-9۰-۹]+|[0-9۰-۹]{1,4}|www\.|https?://|"
    r"کپی\s*برداری|تمام\s+حقوق\s+محفوظ|پایان\s+سند)\s*$",
    re.I,
)
_TRAINING = re.compile(
    r"این\s+مجموعه\s+برای\s+آموزش|آموزش\s+و\s+تمرین\s+کارآموزان|"
    r"پرونده\s+آموزشی|صرفاً\s+برای\s+آموزش|فقط\s+برای\s+آموزش|"
    r"نمونه\s+(?:آموزشی|تمرینی)|تمرین\s+کارآموزی",
    re.I,
)


def _norm_line(line: str) -> str:
    line = re.sub(r"\s+", " ", str(line or "")).strip(" -•▪◦\t")
    return line


def _is_removable_line(line: str) -> bool:
    if not line:
        return True
    if _STANDALONE_ARTIFACTS.match(line) or _TRAINING.search(line):
        return True
    # Existing source-quality gate is deliberately used only for very short
    # fragments here; long legal paragraphs must never be discarded merely
    # because they contain a number or an unfamiliar OCR token.
    if len(line) < 28 and is_probable_source_noise(line):
        return True
    return False


def segment_document_pages(pages: Iterable[Tuple[int, str]]):
    """Return cleaned ``[(page_no, text), ...]`` plus segmentation diagnostics.

    Repeated lines are treated as page headers/footers only when they occur on
    at least two pages and are short enough to plausibly be an artifact.  This
    avoids deleting a repeated legal sentence that legitimately occurs in a
    pleading.
    """
    original = [(int(p), str(t or "")) for p, t in pages]
    line_counts = Counter()
    for _, text in original:
        seen_on_page = set()
        for raw in text.splitlines():
            line = _norm_line(raw)
            if not line or _PAGE_MARKER.match(line):
                continue
            key = re.sub(r"[0-9۰-۹]+", "#", line)
            if len(line) <= 90 and key not in seen_on_page:
                line_counts[key] += 1
                seen_on_page.add(key)

    repeated = {
        key for key, count in line_counts.items()
        if count >= 2 and (len(key) <= 70 or re.search(r"صفحه|پرونده|دادگستری|www|http", key, re.I))
    }

    result = []
    removed = []
    for page_no, text in original:
        kept = []
        page_removed = []
        for raw in text.splitlines():
            line = _norm_line(raw)
            if not line:
                if kept and kept[-1] != "":
                    kept.append("")
                continue
            if _PAGE_MARKER.match(line):
                continue
            key = re.sub(r"[0-9۰-۹]+", "#", line)
            remove_reason = None
            if _is_removable_line(line):
                remove_reason = "standalone_artifact"
            elif key in repeated and len(line) <= 90:
                remove_reason = "repeated_header_footer"
            if remove_reason:
                page_removed.append({"text": line, "reason": remove_reason})
                continue
            kept.append(line)
        while kept and kept[-1] == "":
            kept.pop()
        cleaned = "\n".join(kept)
        if cleaned.strip():
            result.append((page_no, cleaned))
        removed.append({"page": page_no, "removed": page_removed})

    diag = {
        "input_pages": len(original),
        "output_pages": len(result),
        "repeated_artifact_candidates": sorted(repeated),
        "removed_lines": sum(len(x["removed"]) for x in removed),
        "pages": removed,
    }
    return result, diag
