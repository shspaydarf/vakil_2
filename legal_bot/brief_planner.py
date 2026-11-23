# -*- coding: utf-8 -*-
"""V149 — local-first brief planning layer.

Builds a conservative, reviewable plan before source selection/drafting.
It only extracts information already present in the case/user text and never
invents facts, authorities, or legal conclusions.
"""
from __future__ import annotations

import re
from typing import Dict, List

from .brief_workflow import brief_case_summary, detect_brief_gaps
from .brief_workspace import brief_case_understanding
from .brief_templates import TEMPLATES


def _clean(value: str) -> str:
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def _purpose_for_type(brief_type: str) -> str:
    t = _clean(brief_type)
    if 'پاسخ' in t:
        return 'پاسخ مستند و منظم به ادعاها/مطالب طرف مقابل'
    if 'تجدیدنظر' in t:
        return 'بیان جهات اعتراض و درخواست بررسی/اصلاح رأی مورد اعتراض'
    if 'اعتراض' in t:
        return 'بیان مبنای اعتراض و درخواست تصمیم متناسب با موضوع'
    if 'درخواست' in t:
        return 'تنظیم درخواست روشن، مستند و قابل بررسی'
    if 'مطالبه' in t or 'خواسته' in t:
        return 'بیان مبنای خواسته و ادله پشتیبان آن'
    if 'اعسار' in t or 'تقسیط' in t:
        return 'بیان وضعیت و مستندات مرتبط با اعسار/تقسیط'
    return 'تنظیم دفاعیه منسجم بر پایه اطلاعات و مستندات پرونده'


def _question_for_gap(label: str) -> str:
    mapping = {
        'طرفین': 'نام و سمت دقیق طرفین پرونده چیست؟',
        'موضوع/خواسته': 'موضوع یا خواسته دقیق این لایحه چیست؟',
        'مرجع رسیدگی': 'مرجع رسیدگی، شعبه و در صورت وجود شماره پرونده چیست؟',
        'تاریخ/مهلت مهم': 'کدام تاریخ یا مهلت برای این لایحه اهمیت دارد؟',
        'دلیل یا مستند اصلی': 'مهم‌ترین سند یا دلیل پشتیبان ادعای شما چیست؟',
        'دادنامه/رأی مورد اعتراض': 'شماره/تاریخ دادنامه یا رأی مورد اعتراض چیست؟',
    }
    if label.startswith('اطلاعات قالب: '):
        field = label.split(':', 1)[1].strip()
        return f'برای قالب انتخاب‌شده، اطلاعات «{field}» را در صورت وجود وارد کنید.'
    return mapping.get(label, f'اطلاعات «{label}» را در صورت وجود تکمیل کنید.')


def build_brief_plan(
    facts: str = '',
    brief_type: str = 'لایحه دفاعیه',
    case_text: str = '',
    template_key: str = '',
) -> Dict:
    """Create a deterministic plan from the supplied matter context."""
    facts = _clean(facts)
    case_text = _clean(case_text)
    combined = '\n'.join(x for x in (case_text, facts) if x).strip()
    understanding = brief_case_understanding(combined)
    gaps = detect_brief_gaps(facts, brief_type, case_text, template_key)
    profile = TEMPLATES.get(template_key or '', {}) if template_key else {}

    issues: List[str] = []
    for item in understanding.get('claims', []):
        item = _clean(item)
        if item and item not in issues:
            issues.append(item[:500])
        if len(issues) >= 6:
            break

    known = []
    for key in ('parties', 'claims', 'evidence', 'dates', 'refs'):
        for item in understanding.get(key, [])[:6]:
            item = _clean(item)
            if item and item not in known:
                known.append(item[:500])

    questions = [_question_for_gap(g) for g in gaps[:8]]
    # A plan should not force the lawyer through a questionnaire when the
    # existing matter is already sufficiently populated.
    status = 'needs_input' if gaps else 'ready_for_review'
    if not combined:
        status = 'needs_input'
        questions = ['شرح کوتاه ماجرا، خواسته و مهم‌ترین مدرک/دلیل را وارد کنید.']

    return {
        'version': 149,
        'brief_type': _clean(brief_type) or 'لایحه دفاعیه',
        'template_key': template_key or '',
        'template_title': _clean(profile.get('title') or profile.get('name') or ''),
        'purpose': _purpose_for_type(brief_type),
        'case_summary': brief_case_summary(combined),
        'parties': understanding.get('parties', [])[:6],
        'claims': understanding.get('claims', [])[:8],
        'evidence': understanding.get('evidence', [])[:8],
        'dates': understanding.get('dates', [])[:8],
        'authorities_already_mentioned': understanding.get('refs', [])[:8],
        'issues': issues,
        'missing': gaps[:10],
        'questions': questions,
        'status': status,
        'user_confirmed': False,
    }


def format_brief_plan(plan: Dict) -> str:
    """Render a compact Telegram-friendly plan; no legal conclusions are added."""
    p = plan or {}
    lines = ['🧭 نقشه اولیه لایحه', '']
    lines += [f"📝 نوع: {p.get('brief_type') or 'لایحه دفاعیه'}"]
    if p.get('template_title'):
        lines.append(f"📦 قالب: {p['template_title']}")
    lines += ['', '🎯 هدف پیشنهادی:', p.get('purpose') or 'تنظیم لایحه بر پایه اطلاعات پرونده']

    summary = _clean(p.get('case_summary'))
    if summary:
        lines += ['', '📌 خلاصه پرونده:', summary[:1000]]

    def block(title: str, values: list, icon: str = '•', limit: int = 5):
        if not values:
            return
        lines.extend(['', title])
        for value in values[:limit]:
            lines.append(f'{icon} {_clean(value)[:450]}')

    block('👥 اطلاعات طرفین:', p.get('parties', []), limit=4)
    block('🎯 موضوعات/ادعاهای پیدا‌شده:', p.get('claims', []), limit=5)
    block('📎 ادله/اسناد پیدا‌شده:', p.get('evidence', []), limit=5)
    block('📅 تاریخ‌های مهم پیدا‌شده:', p.get('dates', []), limit=5)
    block('📚 مستندات حقوقی ذکرشده در ورودی:', p.get('authorities_already_mentioned', []), limit=4)

    missing = p.get('missing') or []
    if missing:
        lines += ['', '⚠️ مواردی که فعلاً پیدا نشد:']
        lines += [f'• {x}' for x in missing[:8]]
        lines.append('این موارد «واقعیتِ مفقود» محسوب نمی‌شوند؛ فقط در متن فعلی پیدا نشده‌اند.')

    if p.get('questions'):
        lines += ['', '❓ اگر اطلاعات بالا را دارید، این موارد را تکمیل کنید:']
        lines += [f'{i}) {q}' for i, q in enumerate(p['questions'][:6], 1)]

    if p.get('status') == 'ready_for_review':
        lines += ['', '✅ اطلاعات اولیه برای ادامه کافی به نظر می‌رسد.']
    else:
        lines += ['', '🟡 می‌توانید اطلاعات ناقص را تکمیل کنید یا با همین اطلاعات ادامه دهید.']

    lines += ['', '⚠️ این نقشه پیشنهاد ساختاری است؛ صحت وقایع، سمت‌ها و استنادات باید توسط وکیل تأیید شود.']
    return '\n'.join(lines)
