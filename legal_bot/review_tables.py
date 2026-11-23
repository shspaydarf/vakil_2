"""Conservative, source-linked contract review table builder.

This is a navigation aid over extracted text, not a legal classifier or conclusion.
Unknown fields stay empty and every populated cell carries source context.
"""
from __future__ import annotations
import re
from typing import Any

FIELDS = {
    "parties": ("طرفین", ("طرفین", "طرف قرارداد", "کارفرما", "پیمانکار", "فروشنده", "خریدار", "موجر", "مستأجر", "کارفرما", "متعهد")),
    "contract_date": ("تاریخ قرارداد", ("تاریخ قرارداد", "تاریخ انعقاد", "مورخ", "تاریخ تنظیم")),
    "amount": ("مبلغ و عوض", ("مبلغ قرارداد", "مبلغ کل", "ثمن معامله", "اجاره‌بها", "حق‌الزحمه", "مبلغ", "ریال", "تومان")),
    "payment": ("پرداخت", ("نحوه پرداخت", "پرداخت", "اقساط", "پیش‌پرداخت", "سررسید", "چک")),
    "obligations": ("تعهدات و تحویل", ("تعهد", "موظف", "مکلف", "تحویل", "تسلیم", "انجام موضوع قرارداد", "زمان اجرا")),
    "guarantees": ("تضمین و ضمانت", ("ضمانت", "تضمین", "وجه التزام", "وثیقه", "ضامن", "چک ضمانت", "حسن انجام کار")),
    "termination": ("فسخ و خاتمه", ("فسخ", "انفساخ", "خاتمه", "اقاله", "حق فسخ", "فسخ قرارداد")),
    "disputes": ("حل اختلاف", ("حل اختلاف", "داوری", "داور", "دادگاه صالح", "صلاحیت محلی", "مرجع رسیدگی")),
}


def _page_for(text: str, offset: int) -> int | None:
    page = None
    for match in re.finditer(r'^\s*\[صفحه\s+(\d+)\]\s*$', text[:offset], re.M):
        page = int(match.group(1))
    return page


def build_review_table(documents: list[dict[str, Any]], *, max_documents: int = 50,
                       max_chars_per_document: int = 500_000,
                       max_total_chars: int = 2_000_000) -> dict[str, Any]:
    rows = []
    processed = 0
    for index, doc in enumerate(list(documents or [])[:max(1, min(int(max_documents), 100))]):
        raw = str(doc.get('extracted_text') or '')
        if not raw.strip():
            continue
        allowance = min(len(raw), max(1000, min(int(max_chars_per_document), 1_000_000)),
                        max(0, max_total_chars - processed))
        if allowance <= 0:
            break
        text = raw[:allowance]
        processed += allowance
        cells = {}
        for key, (label, terms) in FIELDS.items():
            matches = []
            seen = set()
            # Retain the containing line/sentence as evidence; do not infer a value.
            for match in re.finditer(r'[^\n.!؟؛]{0,180}(?:' + '|'.join(re.escape(t) for t in sorted(terms, key=len, reverse=True)) + r')[^\n.!؟؛]{0,180}(?:[.!؟؛]|$)', text, re.I):
                snippet = re.sub(r'\s+', ' ', match.group(0)).strip(' ؛،')
                if len(snippet) < 5 or snippet in seen:
                    continue
                seen.add(snippet)
                matches.append({
                    'file_name': str(doc.get('file_name') or doc.get('name') or 'سند بدون نام'),
                    'document_id': doc.get('id', doc.get('document_id')),
                    'page': _page_for(text, match.start()),
                    'snippet': snippet[:360],
                    'source_verified': False,
                })
                if len(matches) >= 5:
                    break
            cells[key] = {'label': label, 'status': 'found' if matches else 'not_found',
                          'value': ' | '.join(x['snippet'] for x in matches), 'sources': matches}
        rows.append({'document_id': doc.get('id', doc.get('document_id')),
                     'file_name': str(doc.get('file_name') or doc.get('name') or 'سند بدون نام'),
                     'truncated': allowance < len(raw), 'text_chars': len(raw),
                     'analyzed_chars': allowance, 'cells': cells})
    return {'columns': [{'key': k, 'label': v[0]} for k, v in FIELDS.items()],
            'rows': rows, 'row_count': len(rows), 'characters_processed': processed,
            'review_required': True,
            'disclaimer': 'این جدول فقط قطعات متنی حاوی واژه‌های مرتبط را گردآوری می‌کند. نبودن داده به معنی نبود شرط در سند نیست؛ هر خانه باید با اصل سند و صفحه مربوط بررسی شود.'}
