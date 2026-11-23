# -*- coding: utf-8 -*-
"""Interactive, deterministic workflow helpers for source-grounded briefs."""
import re
from typing import Dict, List

try:
    from .brief_templates import TEMPLATE_PROFILES, TEMPLATE_FIELD_RULES
except Exception:
    TEMPLATE_PROFILES = {}


def _norm_fa(s: str) -> str:
    s = str(s or '').replace('ي','ی').replace('ك','ک').replace('‌',' ')
    return re.sub(r'\s+', ' ', s).strip().lower()


def detect_brief_gaps(text: str, brief_type: str = '', case_text: str = '', template_key: str = '') -> List[str]:
    """Return only high-value missing fields; never invent values."""
    t = f"{text or ''}\n{case_text or ''}"
    checks = [
        ('طرفین', r'(خواهان|خوانده|شاکی|مشتکی[‌ ]عنه|موکل|موجر|مستأجر|زوج|زوجه)'),
        ('موضوع/خواسته', r'(موضوع|خواسته|تقاضا|درخواست|مطالبه|اعتراض|دفاع)'),
        ('مرجع رسیدگی', r'(دادگاه|شعبه|دادسرا|دیوان عدالت|اجرای احکام|مرجع)'),
        ('تاریخ/مهلت مهم', r'(تاریخ|مورخ|سررسید|ابلاغ|مهلت)'),
        ('دلیل یا مستند اصلی', r'(سند|مدرک|رسید|قرارداد|اظهارنامه|شهادت|کارشناس|پیوست)'),
    ]
    gaps = [label for label, pat in checks if not re.search(pat, t, re.I)]
    if 'تجدیدنظر' in (brief_type or '') and not re.search(r'(دادنامه|رأی|حکم)', t):
        gaps.append('دادنامه/رأی مورد اعتراض')
    profile = TEMPLATE_PROFILES.get(template_key or '', {})
    field_rules = TEMPLATE_FIELD_RULES.get(template_key or '', {})
    nt = _norm_fa(t)
    for item in profile.get('required', []):
        # Prefer semantic regex rules over literal UI labels. This prevents
        # false gaps such as treating "چک شماره ۱۲۳" as missing "شماره/مشخصات چک".
        patterns = field_rules.get(item, [])
        found = any(re.search(pat, nt, re.I) for pat in patterns) if patterns else False
        if not found:
            aliases = [item, item.replace('/', ' '), item.replace(' ', '')]
            parts = [x for x in re.split(r'[/،,؛]+', item) if x.strip()]
            aliases += parts
            found = any(a and _norm_fa(a) in nt for a in aliases)
        if not found:
            label = f'اطلاعات قالب: {item}'
            if label not in gaps:
                gaps.append(label)
    return gaps


def brief_case_summary(text: str) -> str:
    """Small deterministic preview before the user approves source selection."""
    text = re.sub(r'\s+', ' ', text or '').strip()
    if not text:
        return 'اطلاعات متنی پرونده در دسترس نیست.'
    sentences = re.split(r'(?<=[؟.!؛])\s+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) >= 20]
    return ' '.join(sentences[:5])[:1400]


def source_label(src: Dict, index: int) -> str:
    title = str(src.get('law') or src.get('title') or src.get('name') or 'منبع حقوقی').strip()
    art = str(src.get('article') or src.get('ruling_number') or src.get('ماده') or '').strip()
    kind = str(src.get('kind') or '').strip()
    cid = str((src.get('citation') or {}).get('id') or '').strip()
    bits = [f'{index}. {title}']
    if art:
        bits.append(f'— {art}')
    if kind and kind != 'law':
        bits.append(f'[{kind}]')
    if cid:
        bits.append(f'#{cid}')
    return ' '.join(bits)
