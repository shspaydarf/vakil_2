"""Local-first Iranian legal calculation engines.

The functions here are deterministic and deliberately keep legal assumptions
explicit.  They are not an AI opinion engine.  UI handlers may add a source
note and a verification warning where data is time-sensitive.
"""
from datetime import date, timedelta
import re


def parse_amount(value):
    trans = str.maketrans('۰۱۲۳۴۵۶۷۸۹٬،٫', '0123456789,,.')
    s = str(value).translate(trans).replace(',', '').replace('٬','').replace('،','').replace('٫','.')
    s = re.sub(r'[^0-9.]', '', s)
    if not s:
        return None
    try:
        n = float(s)
        return int(round(n)) if n.is_integer() else n
    except ValueError:
        return None


def mahr_value(amount, contract_index, target_index):
    if amount <= 0 or contract_index <= 0 or target_index <= 0:
        raise ValueError('invalid mahr inputs')
    return round(amount * target_index / contract_index)


# Common fixed diyah fractions used by the UI. These are fractions of the
# complete diyah where the statute defines a fixed amount; ارش is intentionally
# excluded because it is not a fixed statutory percentage.
HEAD_WOUND_PCTS = {
    'حارصه': 1, 'دامیه': 2, 'متلاحمه': 3, 'سمحاق': 4, 'موضحه': 5,
    'هاشمه': 10, 'منقله': 15, 'مأمومه': 100/3, 'دامغه': 200/3,
    'جائفه': 100/3,
}

COLOR_PCTS = {'سرخی صورت': 0.15, 'کبودی صورت': 0.30, 'سیاهی صورت': 0.45,
              'سرخی سایر مواضع': 0.15, 'کبودی سایر مواضع': 0.30,
              'سیاهی سایر مواضع': 0.45}


def diyah_percentage(full_diyah, pct):
    if full_diyah <= 0 or pct < 0:
        raise ValueError('invalid diyah inputs')
    return round(full_diyah * float(pct) / 100)


def diyah_items(full_diyah, items):
    """Calculate fixed-percentage items; returns totals and an ارش flag."""
    total = 0
    results = []
    has_ersh = False
    for item in items:
        kind = item.get('kind')
        if kind == 'ارش':
            has_ersh = True
            results.append({'title': item.get('title','ارش'), 'pct': None, 'amount': None, 'ersh': True})
            continue
        pct = float(item['pct'])
        amount = diyah_percentage(full_diyah, pct)
        total += amount
        results.append({'title': item.get('title','آسیب'), 'pct': pct, 'amount': amount, 'ersh': False})
    return {'total': total, 'items': results, 'has_ersh': has_ersh}


# 1405 source data is intentionally stored separately from formulas so it can
# be updated without changing the engine.
DIYA_FULL_1405_NORMAL = 2_100_000_000
DIYA_FULL_1405_HARAM = 2_800_000_000


def court_fee(amount_rial, stage):
    """Current configured 1405 civil filing fee bands.

    stage: first, appeal, supreme, unknown.  The rates are kept configurable
    because annual budget/service tariffs can change.
    """
    if amount_rial < 0:
        raise ValueError('negative amount')
    if stage == 'first':
        threshold = 200_000_000
        rate1, rate2 = 0.025, 0.035
        return round(min(amount_rial, threshold)*rate1 + max(amount_rial-threshold,0)*rate2)
    if stage == 'appeal':
        return round(amount_rial * 0.045)
    if stage in {'supreme','retrial','third_party'}:
        return round(amount_rial * 0.055)
    raise ValueError('unknown stage')


def lawyer_fee_financial(amount_rial):
    """Progressive 1405 tariff table used for a financial civil claim."""
    bands = [(500_000_000, .08), (2_000_000_000, .07), (10_000_000_000, .05),
             (30_000_000_000, .04), (None, .03)]
    remaining = float(amount_rial)
    lower = 0
    total = 0.0
    for upper, rate in bands:
        if upper is None:
            part = max(remaining-lower, 0)
        else:
            part = max(min(remaining, upper)-lower, 0)
        total += part * rate
        if upper is None or remaining <= upper:
            break
        lower = upper
    return round(total)


def lawyer_fee_split(total, first_ratio=.60):
    first = round(total * first_ratio)
    return first, total-first


def parse_iso_date(s):
    m = re.fullmatch(r'\s*(\d{4})[-/](\d{1,2})[-/](\d{1,2})\s*', s)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def add_calendar_days(d, days):
    return d + timedelta(days=int(days))


def alcohol_article_702_fine(value_toman):
    """Article 702 fine for manufacture/purchase/sale/offering/transport/keeping alcoholic beverages.

    The fine is five times the عرفی value of the discovered alcoholic beverage.
    This is a statutory multiplier, not an annually indexed fixed amount.
    """
    value = parse_amount(value_toman)
    if value is None or value <= 0:
        raise ValueError('invalid alcoholic beverage value')
    return int(round(value * 5))


def delay_damage(principal, index_start, index_end):
    """Index-based delay damage estimate: principal * (idx_end/idx_start - 1).

    This mirrors the common index method used with official price indices.
    Caller must supply verified indices; this function does not fetch them.
    """
    p = float(principal)
    a = float(index_start)
    b = float(index_end)
    if p <= 0 or a <= 0 or b <= 0:
        raise ValueError("invalid delay inputs")
    corrected = p * b / a
    return {
        "principal": round(p),
        "corrected": round(corrected),
        "damage": round(corrected - p),
        "index_start": a,
        "index_end": b,
        "formula": "اصل × (شاخص مقصد ÷ شاخص مبدأ) ؛ خسارت = مبلغ تعدیلی − اصل",
    }


CALC_SOURCE_NOTES = {
    "mahr": (
        "مهریه وجه نقد: مبلغ × (شاخص سال محاسبه ÷ شاخص سال عقد). "
        "شاخص از سری بسته‌شده در بات؛ سال‌های ۱۴۰۳ و ۱۴۰۴ برچسب تقریبی دارند و باید با جدول بانک مرکزی/مرجع رسمی تطبیق شوند."
    ),
    "delay": (
        "خسارت تأخیر تأدیه شاخص‌محور: اصل × (شاخص مقصد ÷ شاخص مبدأ). "
        "شاخص را از منبع رسمی وارد کنید؛ بات عدد شاخص را از اینترنت نمی‌گیرد."
    ),
    "diya": (
        "دیه کامل ۱۴۰۵: غیرحرام ۲٫۱ میلیارد و حرام ۲٫۸ میلیارد تومان (ابلاغ قوه قضاییه). ارش عددسازی نمی‌شود."
    ),
    "fee": (
        "هزینه دادرسی بر اساس فرمول پیکربندی‌شده بودجه/تعرفه جاری در بسته (مبالغ ریال). تعرفه شعبه ممکن است متفاوت باشد."
    ),
    "lawyer": (
        "حق‌الوکاله پلکانی بر اساس آیین‌نامه تعرفه؛ توافق وکیل و موکل می‌تواند متفاوت باشد."
    ),
}
