"""Conservative, local-first "next step" analysis for a case.

This module never invents procedural status or legal obligations. It only turns
explicit signals found in the stored case text into a short, actionable view.
"""
from __future__ import annotations

import re
from datetime import date
from .calendar_dates import extract_important_dates
from .files import clean_fa

RULES = [
    ("دادخواست/شروع دعوا", r"دادخواست|ثبت دادخواست|دادخواست تقدیم|طرح دعوا"),
    ("ابلاغ", r"ابلاغ|تاریخ ابلاغ|ابلاغیه"),
    ("جلسه رسیدگی", r"جلسه\s+(?:رسیدگی|دادگاه|دادرسی)|وقت\s+رسیدگی"),
    ("رأی/حکم", r"رأی|رای|حکم|دادنامه|محکومیت"),
    ("اجرای حکم", r"اجراییه|اجرای\s+حکم|اجرای\s+دادنامه|اجرائیه"),
    ("قرارداد", r"قرارداد|عقد|طرفین قرارداد|متعهد|متعهدله"),
    ("فسخ/خاتمه", r"فسخ|اقاله|انفساخ|خاتمه قرارداد|انحلال قرارداد"),
    ("مطالبه/پرداخت", r"مطالبه|پرداخت|تأدیه|تادیه|قسط|اقساط|سررسید|چک|سفته"),
    ("خسارت", r"خسارت|وجه التزام|وجه‌التزام|جریمه تأخیر|جریمه تاخیر"),
    ("اظهارنامه", r"اظهارنامه"),
]

ACTIONS = [
    (r"اجراییه|اجرای\s+حکم|اجرای\s+دادنامه|اجرائیه", "بررسی وضعیت اجرای حکم و مستندات مربوط به اجرای آن."),
    (r"جلسه\s+(?:رسیدگی|دادگاه|دادرسی)|وقت\s+رسیدگی", "بررسی تاریخ جلسه و آماده‌سازی مدارک و دفاع مرتبط با موضوع جلسه."),
    (r"ابلاغ|تاریخ ابلاغ|ابلاغیه", "بررسی متن ابلاغ و کنترل مهلت یا اقدام احتمالی ناشی از آن."),
    (r"دادخواست|ثبت دادخواست|دادخواست تقدیم|طرح دعوا", "بررسی خواسته، طرفین، مستندات و وضعیت ثبت/رسیدگی دعوا."),
    (r"رأی|رای|حکم|دادنامه|محکومیت", "بررسی متن کامل رأی، تاریخ ابلاغ و مواردی که ممکن است نیازمند اقدام بعدی باشند."),
    (r"سررسید|مهلت|موعد|تا\s+تاریخ", "کنترل تاریخ و مهلت مرتبط و ثبت اقدام لازم پیش از سررسید، در صورت احراز آن از متن."),
    (r"چک|سفته|پرداخت|تأدیه|تادیه|قسط|اقساط|مطالبه", "بررسی وضعیت پرداخت/تعهد و مستندات مربوط به مطالبه یا انجام تعهد."),
    (r"فسخ|اقاله|انفساخ|خاتمه قرارداد", "بررسی بندهای قرارداد و مستندات مربوط به پایان یا برهم‌خوردن رابطه قراردادی."),
    (r"قرارداد|عقد|متعهد|متعهدله", "مرور تعهدات، سررسیدها، ضمانت‌اجراها و مدارک قرارداد."),
]


def _sentences(text: str):
    text = clean_fa(text or "")
    chunks = re.split(r'(?<=[.!؟؛])\s+|[\r\n]+', text)
    return [re.sub(r'\s+', ' ', x).strip(' -•▪◦') for x in chunks if len(re.sub(r'\s+', ' ', x).strip()) >= 20]


def _signal_lines(text: str, limit: int = 5):
    out=[]; seen=set()
    for sentence in _sentences(text):
        if any(re.search(p, sentence, re.I) for _,p in RULES):
            key=sentence[:350]
            if key not in seen:
                seen.add(key); out.append(sentence[:500])
            if len(out)>=limit: break
    return out


def _stage(text: str):
    found=[]
    for label, pattern in RULES:
        if re.search(pattern, text, re.I):
            found.append(label)
    # Prefer a procedural signal over a generic contract/payment signal.
    priority = ["اجرای حکم", "رأی/حکم", "جلسه رسیدگی", "ابلاغ", "دادخواست/شروع دعوا", "اظهارنامه", "فسخ/خاتمه", "مطالبه/پرداخت", "قرارداد"]
    for item in priority:
        if item in found:
            return item, found
    return (found[0] if found else "مرحله نامشخص"), found


def _action(text: str):
    for pattern, action in ACTIONS:
        if re.search(pattern, text, re.I):
            return action
    return "ابتدا اطلاعات و مستندات اصلی پرونده را مرور و موارد ناقص یا مبهم را مشخص کنید."


def _missing(text: str, stage: str):
    checks = []
    if stage in {"جلسه رسیدگی", "ابلاغ", "دادخواست/شروع دعوا", "رأی/حکم", "اجرای حکم"} and not re.search(r"تاریخ|\d{4}[/-]\d{1,2}[/-]\d{1,2}|\d{1,2}\s*(?:فروردین|اردیبهشت|خرداد|تیر|مرداد|شهریور|مهر|آبان|آذر|دی|بهمن|اسفند)", text):
        checks.append("تاریخ یا مهلت مرتبط در متن فعلی روشن نیست")
    if stage in {"دادخواست/شروع دعوا", "رأی/حکم", "اجرای حکم"} and not re.search(r"خواهان|شاکی|خوانده|محکوم|مشتکی|طرفین", text):
        checks.append("مشخصات نقش طرفین در متن فعلی روشن نیست")
    if stage in {"قرارداد", "فسخ/خاتمه", "مطالبه/پرداخت"} and not re.search(r"مبلغ|تومان|ریال|ثمن|اجرت|تعهد", text):
        checks.append("جزئیات مالی یا تعهد اصلی در متن فعلی روشن نیست")
    return checks[:3]


def analyze_next_step(text: str, max_chars: int = 14000):
    text = clean_fa(text or "")[:max_chars]
    if len(text.strip()) < 40:
        return {"sufficient": False, "reason": "متن پرونده برای تشخیص قدم بعدی کافی نیست."}

    stage, signals = _stage(text)
    action = _action(text)
    try:
        dates = extract_important_dates(text, 12)
    except Exception:
        # Keep the feature usable even when the optional Jalali converter is
        # unavailable; do not pretend we know whether the date is in the future.
        dates = []
        for raw in re.findall(r'(?<!\d)([۰-۹0-9]{4}[/-][۰-۹0-9]{1,2}[/-][۰-۹0-9]{1,2})(?!\d)', text):
            if not any(d.get('raw_value') == raw for d in dates):
                dates.append({'date_jalali': raw, 'date_gregorian': None, 'description': 'تاریخ ذکرشده در پرونده', 'raw_value': raw})
    today = date.today()
    future = []
    for d in dates:
        try:
            if date.fromisoformat(d["date_gregorian"]) >= today:
                future.append(d)
        except Exception:
            pass
    future.sort(key=lambda x: x.get("date_gregorian") or "9999-99-99")
    mentioned_dates = [d for d in dates if not d.get("date_gregorian")]
    missing = _missing(text, stage)
    evidence = _signal_lines(text, 4)

    return {
        "sufficient": bool(signals),
        "stage": stage,
        "signals": signals,
        "action": action,
        "future_dates": future[:3],
        "mentioned_dates": mentioned_dates[:3],
        "missing": missing,
        "evidence": evidence,
    }


def format_next_step(result):
    if not result.get("sufficient"):
        return "➡️ قدم بعدی پرونده\n\n⚠️ اطلاعات فعلی پرونده برای پیشنهاد یک قدم مشخص کافی نیست.\n\nپیشنهاد: متن یا مستندات مرتبط بیشتری به همین پرونده اضافه کنید."

    lines=["➡️ قدم بعدی پرونده", "", f"📌 وضعیت قابل تشخیص از متن: {result['stage']}", "", f"➡️ اقدام پیشنهادی: {result['action']}"]
    if result.get("future_dates"):
        lines += ["", "⏰ تاریخ‌های نزدیک/پیش‌رو که در متن پرونده پیدا شد:"]
        for d in result["future_dates"]:
            lines.append(f"• {d['date_jalali']} — {d['description']}")
    if result.get("missing"):
        lines += ["", "⚠️ مواردی که در متن فعلی روشن نیست:"]
        lines += [f"• {x}" for x in result["missing"]]
    if result.get("evidence"):
        lines += ["", "📄 مبنای این پیشنهاد از متن پرونده:"]
        for x in result["evidence"][:3]:
            lines.append(f"• {x[:320]}")
    lines += ["", "⚖️ توجه: این خروجی فقط بر اساس اطلاعات ثبت‌شده در پرونده تهیه شده و تصمیم حقوقی قطعی یا جایگزین بررسی وکیل/مرجع رسمی نیست."]
    return "\n".join(lines)
