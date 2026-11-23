# -*- coding: utf-8 -*-
"""Conservative source-segment quality gates for extracted legal text.

This layer does not rewrite facts.  It only decides whether a short extracted
segment is safe enough to surface as a source signal.  Raw document text stays
unchanged for audit/provenance.
"""
from __future__ import annotations

import re
from typing import Any

_EDUCATIONAL = re.compile(
    r"این\s+مجموعه\s+برای\s+آموزش|آموزش\s+و\s+تمرین\s+کارآموزان|"
    r"پرونده\s+آموزشی|صرفاً\s+برای\s+آموزش|فقط\s+برای\s+آموزش|"
    r"نمونه\s+(?:آموزشی|تمرینی)|تمرین\s+کارآموزی",
    re.I,
)
_HEADER_FOOTER = re.compile(
    r"^\s*(?:صفحه\s*[0-9۰-۹]+|www\.|https?://|www\s+\S+|"
    r"کپی\s+برداری|تمام\s+حقوق\s+محفوظ|پایان\s+سند)\s*$",
    re.I,
)
_ORPHAN = re.compile(
    r"^\s*(?:تجدیدنظرخواهی|واخواهی|فرجام(?:خواهی)?|اعتراض)\s+[0-9۰-۹]{1,4}\s*$|"
    r"^\s*(?:خدمات|خانواده)\s+(?:اعتراض|ارجاع)\s+کرد\s*$",
    re.I,
)
_KNOWN_OCR_GLUING = re.compile(r"(?:از\s+سال|از\s+تاریخ)\s+(?:مهریه|نفقه|طلاق)\s+[0-9۰-۹]{4}")


def _clean(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip(" -•▪◦")


def is_probable_source_noise(text: Any) -> bool:
    """Return True only for high-signal OCR/header/training artifacts."""
    t = _clean(text)
    if not t:
        return True
    if _EDUCATIONAL.search(t) or _HEADER_FOOTER.search(t) or _ORPHAN.search(t):
        return True
    if _KNOWN_OCR_GLUING.search(t):
        return True
    # Number-heavy fragments are useful when they have a real label/context;
    # reject only very short, mostly numeric fragments.
    alpha = len(re.findall(r"[آ-یA-Za-z]", t))
    digits = len(re.findall(r"[0-9۰-۹]", t))
    words = re.findall(r"[آ-یA-Za-z]{2,}", t)
    if len(t) < 20 and (len(words) <= 2 or digits >= alpha):
        return True
    if alpha < 8 and digits > max(8, alpha * 2):
        return True
    return False


def source_segment_ok(text: Any, *, min_chars: int = 20) -> bool:
    """Conservative visibility gate; it never changes the underlying text."""
    t = _clean(text)
    if len(t) < min_chars:
        return False
    return not is_probable_source_noise(t)
