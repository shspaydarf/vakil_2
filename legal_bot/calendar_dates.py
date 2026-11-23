"""Local-first Persian/Jalali date parsing and important-date extraction.

The bot does not send scheduled Telegram reminders. Dates are extracted from
case text and stored for the user to review when they open the menu item.
"""
from __future__ import annotations

import re
from datetime import date

try:
    import jdatetime as _jdatetime
except Exception:  # pragma: no cover - deployment installs it from requirements
    _jdatetime = None

MONTHS = {
    'فروردین': 1, 'اردیبهشت': 2, 'خرداد': 3, 'تیر': 4, 'مرداد': 5,
    'شهریور': 6, 'مهر': 7, 'آبان': 8, 'آذر': 9, 'دی': 10, 'بهمن': 11, 'اسفند': 12,
}
_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')

IMPORTANT_HINTS = [
    ('جلسه رسیدگی', r'جلسه\s+(?:رسیدگی|دادگاه|دادرسی)|وقت\s+رسیدگی'),
    ('ابلاغ/تاریخ ابلاغ', r'ابلاغ|تاریخ\s+ابلاغ'),
    ('مهلت/موعد', r'مهلت|موعد|سررسید|ظرف\s+مدت|تا\s+تاریخ'),
    ('پرداخت/سررسید پرداخت', r'پرداخت|تادیه|تأدیه|قسط|اقساط|چک|سفته'),
    ('رأی/حکم', r'رأی|رای|حکم|دادنامه|صدور\s+رأی|صدور\s+حکم'),
    ('قرارداد', r'قرارداد|عقد|انعقاد|تنظیم\s+قرارداد'),
    ('دادخواست/دادرسی', r'دادخواست|دادرس|دادرسی|ثبت\s+دادخواست|طرح\s+دعوا'),
    ('اظهارنامه', r'اظهارنامه'),
    ('اجرای حکم', r'اجراییه|اجرای\s+حکم|اجرای\s+دادنامه'),
    ('تاریخ سند/مدرک', r'تاریخ\s+(?:سند|مدرک|صدور|تنظیم)'),
]


def normalize_digits(value: str) -> str:
    return str(value or '').translate(_DIGITS)


_JALAALI_BREAKS = [-61, 9, 38, 199, 426, 686, 756, 818, 1111, 1181, 1210, 1635, 2060, 2097, 2192, 2262, 2324, 2394, 2456, 3178]

def _div(a, b):
    return int(a / b)

def _mod(a, b):
    return a - _div(a, b) * b

def _jal_cal(jy):
    if jy < _JALAALI_BREAKS[0] or jy >= _JALAALI_BREAKS[-1]:
        raise ValueError('سال شمسی خارج از بازه پشتیبانی است.')
    gy = jy + 621
    leap_j = -14
    jp = _JALAALI_BREAKS[0]
    jump = 0
    for jm in _JALAALI_BREAKS[1:]:
        jump = jm - jp
        if jy < jm:
            break
        leap_j += _div(jump, 33) * 8 + _div(_mod(jump, 33), 4)
        jp = jm
    n = jy - jp
    leap_j += _div(n, 33) * 8 + _div(_mod(n, 33) + 3, 4)
    if _mod(jump, 33) == 4 and jump - n == 4:
        leap_j += 1
    leap_g = _div(gy, 4) - _div((_div(gy, 100) + 1) * 3, 4) - 150
    march = 20 + leap_j - leap_g
    return gy, march

def _j2d(jy, jm, jd):
    gy, march = _jal_cal(jy)
    return _g2d(gy, 3, march) + (jm - 1) * 31 - _div(jm, 7) * (jm - 7) + jd - 1

def _g2d(gy, gm, gd):
    d = _div((gy + _div(gm - 8, 6) + 100100) * 1461, 4) + _div(153 * _mod(gm + 9, 12) + 2, 5) + gd - 34840408
    d = d - _div(_div(gy + 100100 + _div(gm - 8, 6), 100) * 3, 4) + 752
    return d

def _d2g(jdn):
    j = 4 * jdn + 139361631
    j = j + _div(_div(4 * jdn + 183187720, 146097) * 3, 4) * 4 - 3908
    i = _div(_mod(j, 1461), 4) * 5 + 308
    gd = _div(_mod(i, 153), 5) + 1
    gm = _mod(_div(i, 153), 12) + 1
    gy = _div(j, 1461) - 100100 + _div(8 - gm, 6)
    return date(gy, gm, gd)

def _d2j(jdn):
    g = _d2g(jdn)
    jy = g.year - 621
    gy, march = _jal_cal(jy)
    jdn1f = _g2d(gy, 3, march)
    k = jdn - jdn1f
    if k >= 0:
        if k <= 185:
            return jy, 1 + _div(k, 31), _mod(k, 31) + 1
        k -= 186
    else:
        jy -= 1
        k += 179
        if _jal_cal(jy)[1] != _jal_cal(jy + 1)[1]:
            k += 1
    return jy, 7 + _div(k, 30), _mod(k, 30) + 1

def jalali_to_gregorian(y: int, m: int, d: int) -> date:
    if _jdatetime:
        return _jdatetime.date(y, m, d).togregorian()
    return _d2g(_j2d(int(y), int(m), int(d)))


def gregorian_to_jalali(d: date):
    if _jdatetime:
        j = _jdatetime.date.fromgregorian(date=d)
        return j.year, j.month, j.day
    return _d2j(_g2d(d.year, d.month, d.day))

def parse_gregorian(value: str):
    s = normalize_digits(value).strip()
    m = re.fullmatch(r'(19\d{2}|20\d{2})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{1,2})', s)
    if not m:
        return None
    y, mo, d = map(int, m.groups())
    return y, mo, d, date(y, mo, d)


def parse_jalali(value: str):
    s = normalize_digits(value).strip()
    m = re.fullmatch(r'(1[234]\d{2})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{1,2})', s)
    if m:
        y, mo, d = map(int, m.groups())
        return y, mo, d, jalali_to_gregorian(y, mo, d)
    m = re.fullmatch(r'(\d{1,2})\s*(فروردین|اردیبهشت|خرداد|تیر|مرداد|شهریور|مهر|آبان|آذر|دی|بهمن|اسفند)\s*(1[234]\d{2})', s)
    if m:
        d, month_name, y = m.groups()
        mo = MONTHS[month_name]
        d = int(d); y = int(y)
        return y, mo, d, jalali_to_gregorian(y, mo, d)
    return None


def _pages(text: str):
    ms = list(re.finditer(r'\[صفحه\s+(\d+)\]', text or ''))
    if not ms:
        return [(None, text or '')]
    out = []
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(text)
        body = text[m.end():end].strip()
        if body:
            out.append((int(m.group(1)), body))
    return out


def _sentence_for_match(body: str, start: int, end: int) -> str:
    left = max(body.rfind('\n', 0, start), body.rfind('؟', 0, start), body.rfind('.', 0, start), body.rfind('؛', 0, start))
    rights = [x for x in (body.find('\n', end), body.find('؟', end), body.find('.', end), body.find('؛', end)) if x >= 0]
    right = min(rights) if rights else len(body)
    return re.sub(r'\s+', ' ', body[left + 1:right]).strip()


def extract_important_dates(text: str, limit: int = 40):
    """Extract dates with meaningful legal/case context, preserving provenance."""
    results = []
    seen = set()
    date_patterns = [
        re.compile(r'(?<!\d)([۰-۹0-9]{4}[/-][۰-۹0-9]{1,2}[/-][۰-۹0-9]{1,2})(?!\d)'),
        re.compile(r'(?<!\d)([۰-۹0-9]{1,2}\s*(?:فروردین|اردیبهشت|خرداد|تیر|مرداد|شهریور|مهر|آبان|آذر|دی|بهمن|اسفند)\s*[۰-۹0-9]{4})(?!\d)'),
    ]
    for page, body in _pages(text):
        for pat in date_patterns:
            for m in pat.finditer(body):
                raw = m.group(1)
                parsed = parse_jalali(raw)
                source_is_jalali = bool(parsed)
                if not parsed:
                    parsed = parse_gregorian(raw)
                if not parsed:
                    continue
                sentence = _sentence_for_match(body, m.start(), m.end())
                context = sentence[:700]
                labels = [label for label, hint in IMPORTANT_HINTS if re.search(hint, context, re.I)]
                if not labels:
                    continue
                y, mo, d, g = parsed
                if source_is_jalali:
                    jy, jm, jd = y, mo, d
                else:
                    jy, jm, jd = gregorian_to_jalali(g)
                key = (g.isoformat(), page, sentence[:250])
                if key in seen:
                    continue
                seen.add(key)
                results.append({
                    'date_jalali': f'{jy:04d}/{jm:02d}/{jd:02d}',
                    'date_gregorian': g.isoformat(),
                    'description': labels[0],
                    'source_page': page,
                    'source_text': context,
                    'raw_value': raw,
                })
                if len(results) >= limit:
                    return results
    return results
