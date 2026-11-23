# -*- coding: utf-8 -*-
"""Phase 10.4.10: conservative structural segmentation of extracted legal text.

Offline proposal only. Original text and character offsets are preserved; no
legal interpretation, automatic correction, or active-bank write is performed.
"""
from __future__ import annotations
import argparse, hashlib, json, re
from pathlib import Path
from typing import Any

class DocumentStructureError(ValueError):
    pass

_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
_PATTERNS = [
    ('article', re.compile(r'^\s*(?:ماده|مادّه)\s*([0-9۰-۹٠-٩]+)?\s*[:：ـ.\-]?\s*(.*)$')),
    ('note', re.compile(r'^\s*(?:تبصره)\s*([0-9۰-۹٠-٩]+)?\s*[:：ـ.\-]?\s*(.*)$')),
    ('clause', re.compile(r'^\s*(?:بند)\s*([0-9۰-۹٠-٩]+|[الف-ی])\s*[:：ـ.\-]?\s*(.*)$')),
    ('chapter', re.compile(r'^\s*(?:فصل|باب|بخش)\s+(.+?)\s*$')),
    ('appendix', re.compile(r'^\s*(?:پیوست|ضمیمه)\s*([0-9۰-۹٠-٩]*)\s*[:：ـ.\-]?\s*(.*)$')),
    ('preamble', re.compile(r'^\s*(?:مقدمه|با توجه به|در اجرای)\s*(.*)$')),
    ('signature', re.compile(r'^\s*(?:امضاء|امضا|رئیس|وزیر|رئیس‌جمهور|رییس جمهور)\s*[:：ـ]?\s*(.*)$')),
]

def segment_text(text: str) -> dict[str, Any]:
    if not isinstance(text, str) or not text.strip():
        raise DocumentStructureError('متن استخراج‌شده خالی یا نامعتبر است')
    lines = []
    offset = 0
    for raw in text.splitlines(keepends=True):
        content = raw.rstrip('\r\n')
        if content.strip():
            lines.append((content, offset, offset + len(content)))
        offset += len(raw)
    segments = []
    current = None
    parent_article = None
    for content, start, end in lines:
        kind, number, title = 'body', None, None
        for candidate, pattern in _PATTERNS:
            match = pattern.match(content)
            if match:
                kind = candidate
                groups = match.groups()
                if candidate == 'chapter':
                    title = groups[0]
                else:
                    number = groups[0] if len(groups) > 1 else None
                    title = groups[1] if len(groups) > 1 else groups[0]
                break
        if kind == 'article':
            parent_article = _norm(number)
        record = {'type': kind, 'start': start, 'end': end, 'text': content,
                  'number': _norm(number) if number else None, 'title_or_remainder': title or None,
                  'parent_article': parent_article if kind in ('note', 'clause') else None,
                  'review_required': kind in ('body', 'preamble', 'signature')}
        segments.append(record)
    return {'segments': segments, 'segment_count': len(segments),
            'article_count': sum(s['type'] == 'article' for s in segments),
            'note_count': sum(s['type'] == 'note' for s in segments),
            'clause_count': sum(s['type'] == 'clause' for s in segments),
            'appendix_count': sum(s['type'] == 'appendix' for s in segments),
            'unclassified_count': sum(s['type'] == 'body' for s in segments),
            'structure_is_verified': False}

def _norm(value: str | None) -> str | None:
    return value.translate(_DIGITS) if value else None

def structure_extraction(extraction: dict[str, Any], identity: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(extraction, dict) or extraction.get('phase') != '10.4.7':
        raise DocumentStructureError('خروجی معتبر فاز ۱۰.۴.۷ لازم است')
    if extraction.get('active_bank_write') is not False or extraction.get('legal_authenticity_verified') is not False:
        raise DocumentStructureError('ورودی باید صراحتاً در قرنطینه باشد')
    digest = extraction.get('source_pdf_sha256')
    if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise DocumentStructureError('هش سند معتبر نیست')
    if identity and (identity.get('phase') != '10.4.9' or identity.get('source_pdf_sha256') != digest):
        raise DocumentStructureError('گزارش هویت با سند تطبیق ندارد')
    pages = extraction.get('pages')
    if not isinstance(pages, list) or not pages:
        raise DocumentStructureError('صفحات استخراج‌شده موجود نیست')
    page_results = []
    for page in pages:
        if not isinstance(page, dict) or not isinstance(page.get('selected_text'), str):
            raise DocumentStructureError('ساختار صفحه استخراج‌شده نامعتبر است')
        page_results.append({'page_number': page.get('page_number'), **segment_text(page['selected_text'])})
    return {'phase': '10.4.10', 'source_pdf_sha256': digest,
            'source_url': extraction.get('source_url'), 'pages': page_results,
            'identity_proposal_attached': identity is not None,
            'legal_authenticity_verified': False, 'active_bank_write': False,
            'human_review_required': True}

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('extraction_json'); parser.add_argument('--identity-json'); parser.add_argument('--output', required=True)
    args = parser.parse_args()
    extraction = json.loads(Path(args.extraction_json).read_text(encoding='utf-8'))
    identity = json.loads(Path(args.identity_json).read_text(encoding='utf-8')) if args.identity_json else None
    result = structure_extraction(extraction, identity)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
