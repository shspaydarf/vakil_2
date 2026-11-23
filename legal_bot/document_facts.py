"""Conservative, source-linked fact candidates extracted from legal documents.

These are suggestions for human review, not verified facts or legal deadlines.
Every candidate retains its page and verbatim context so the reviewer can
check it against the original document.
"""
from __future__ import annotations
import re
from bisect import bisect_right
from typing import Any

_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
_DATE = re.compile(r'(?<!\d)(\d{1,4})\s*[/\-\.٫]\s*(\d{1,2})\s*[/\-\.٫]\s*(\d{1,4})(?!\d)')
_AMOUNT = re.compile(r'(?<!\w)([۰-۹٠-٩0-9][۰-۹٠-٩0-9٬,،\.٫ ]{0,18}[۰-۹٠-٩0-9])\s*(ریال|تومان)(?!\w)')
_NATIONAL_ID = re.compile(r'(?:کد\s*ملی|شناسه\s*ملی)\s*[:：]?\s*([۰-۹٠-٩0-9\s-]{10,16})')
_PHONE = re.compile(r'(?:تلفن|موبایل|همراه|شماره\s*تماس)\s*[:：]?\s*((?:\+?۹۸|\+?98|0)?[۰-۹٠-٩0-9\s-]{8,15})')
_NAME = re.compile(r'(?:نام\s*(?:و\s*نام\s*خانوادگی)?|خواهان|خوانده|موکل|وکیل|کارفرما|کارگر)\s*[:：]?\s*([^\n،؛]{2,70})')
_PAGE = re.compile(r'^\s*\[صفحه\s+(\d+)\]\s*$', re.M)


def _norm_digits(value: str) -> str:
    return (value or '').translate(_DIGITS)


def _page_at(page_offsets: list[int], page_numbers: list[int], offset: int) -> int | None:
    """Return nearest preceding page marker in O(log n), not rescanning text."""
    index = bisect_right(page_offsets, offset) - 1
    return page_numbers[index] if index >= 0 else None


def _context(text: str, start: int, end: int, radius: int = 85) -> str:
    return re.sub(r'\s+', ' ', text[max(0, start-radius):min(len(text), end+radius)]).strip()[:220]


def extract_document_facts(text: str, limit: int = 40) -> list[dict[str, Any]]:
    """Extract high-signal candidates with conservative confidence labels."""
    source = str(text or '')
    found: list[dict[str, Any]] = []
    page_markers = list(_PAGE.finditer(source))
    page_offsets = [m.start() for m in page_markers]
    page_numbers = [int(m.group(1)) for m in page_markers]

    def add(kind: str, match: re.Match, value: str, confidence: float, normalized: str | None = None, calendar_system: str | None = None):
        page = _page_at(page_offsets, page_numbers, match.start())
        found.append({
            'type': kind, 'value': value.strip(), 'normalized_value': normalized,
            'page': page, 'snippet': _context(source, match.start(), match.end()),
            'confidence': round(confidence, 2), 'calendar_system': calendar_system, 'status': 'needs_review',
            'review_required': True, '_offset': match.start(),
        })

    for m in _DATE.finditer(source):
        raw = m.group(0).strip()
        nums = [_norm_digits(x) for x in m.groups()]
        # Preserve component order but do not convert calendar systems: Iranian
        # legal documents commonly use Solar Hijri dates, and guessing Gregorian
        # would silently corrupt deadlines.
        if len(nums[0]) == 4:
            norm = f'{nums[0]}-{int(nums[1]):02d}-{int(nums[2]):02d}'
        elif len(nums[2]) == 4:
            norm = f'{nums[2]}-{int(nums[1]):02d}-{int(nums[0]):02d}'
        else:
            norm = None
        add('date', m, raw, 0.78 if norm else 0.48, norm, 'unknown' if norm else None)

    for m in _AMOUNT.finditer(source):
        raw_num = _norm_digits(m.group(1))
        digits = re.sub(r'[^0-9]', '', raw_num)
        unit = m.group(2)
        # Punctuation can mean either decimal or thousands grouping. Preserve the
        # candidate for review, but do not normalize punctuated values for cross-doc
        # matching: stripping separators could equate 1.000 with 1000 incorrectly.
        has_ambiguous_separator = bool(re.search(r'[,،٬٫.]', raw_num))
        normalized = f'{digits} {unit}' if digits and not has_ambiguous_separator else None
        add('amount', m, m.group(0), 0.84, normalized)

    for m in _NATIONAL_ID.finditer(source):
        value = re.sub(r'\D', '', _norm_digits(m.group(1)))
        add('national_id', m, m.group(0), 0.68 if len(value) == 10 else 0.35, value or None)

    for m in _PHONE.finditer(source):
        value = re.sub(r'\D', '', _norm_digits(m.group(1)))
        add('phone', m, m.group(0), 0.62 if 10 <= len(value) <= 13 else 0.35, value or None)

    for m in _NAME.finditer(source):
        value = re.sub(r'\s+', ' ', m.group(1)).strip(' :：-')
        # A name-like label may capture field noise or prose; intentionally low confidence.
        if value and not re.fullmatch(r'[\d\W_]+', value):
            add('person_or_party', m, value, 0.52, None)

    # Deduplicate repeated candidates while preserving source order/provenance.
    seen = set(); result = []
    for item in sorted(found, key=lambda x: x['_offset']):
        key = (item['type'], item['value'], item['page'])
        if key in seen:
            continue
        seen.add(key); item.pop('_offset', None); result.append(item)
        if len(result) >= max(1, min(int(limit), 100)):
            break
    return result
