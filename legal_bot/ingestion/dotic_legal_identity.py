# -*- coding: utf-8 -*-
"""Phase 10.4.9: conservative, evidence-backed legal document classification.

Offline only. Produces proposals; never certifies legal authenticity/status and
never writes to active legal banks. Stable identity is withheld unless all
required issuer/kind/official-number/date fields are independently present.
"""
from __future__ import annotations
import argparse, hashlib, json, re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

class LegalIdentityError(ValueError):
    pass

_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
_DATE_RE = re.compile(r'(?<!\d)(13\d{2}|14\d{2})[/-](0?[1-9]|1[0-2])[/-](0?[1-9]|[12]\d|3[01])(?!\d)')
_NUMBER_PATTERNS = [
    re.compile(r'(?:شماره\s*(?:دادنامه|رأی|رای|نامه|بخشنامه)?\s*[:：]?\s*)([0-9۰-۹٠-٩][0-9۰-۹٠-٩/\-]*)', re.I),
    re.compile(r'(?:دادنامه\s*شماره\s*)([0-9۰-۹٠-٩][0-9۰-۹٠-٩/\-]*)', re.I),
]

DOC_RULES = [
    ('supreme_court_unity_ruling', ['رأی وحدت رویه هیأت عمومی دیوان عالی کشور', 'رای وحدت رویه هیات عمومی دیوان عالی کشور', 'هیأت عمومی دیوان عالی کشور']),
    ('administrative_justice_general_assembly_ruling', ['رأی هیأت عمومی دیوان عدالت اداری', 'رای هیات عمومی دیوان عدالت اداری', 'هیأت عمومی دیوان عدالت اداری']),
    ('judiciary_advisory_opinion', ['نظریه مشورتی اداره کل حقوقی قوه قضاییه', 'اداره کل حقوقی قوه قضاییه', 'نظریه مشورتی']),
    ('regulation_or_by law', ['آیین نامه', 'آیین‌نامه', 'تصویب نامه', 'تصویب‌نامه', 'اساسنامه']),
    ('parliamentary_law', ['قانون', 'مصوب مجلس شورای اسلامی', 'مجلس شورای اسلامی']),
]

ISSUERS = [
    ('supreme_court', ['دیوان عالی کشور']),
    ('administrative_justice_court', ['دیوان عدالت اداری']),
    ('judiciary_legal_department', ['اداره کل حقوقی قوه قضاییه', 'معاونت حقوقی قوه قضاییه']),
    ('parliament', ['مجلس شورای اسلامی']),
    ('government', ['هیأت وزیران', 'هیات وزیران', 'هیئت وزیران', 'وزارت دادگستری']),
]

def _norm_digits(s: str) -> str:
    return s.translate(_DIGITS)

def _find_unique(text: str, rules: list[tuple[str, list[str]]]) -> tuple[str | None, list[str]]:
    hits = [(key, term) for key, terms in rules for term in terms if term in text]
    keys = sorted({key for key, _ in hits})
    return (keys[0] if len(keys) == 1 else None), [term for _, term in hits]

def classify_extraction(extraction: dict[str, Any], quality: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(extraction, dict) or extraction.get('phase') != '10.4.7':
        raise LegalIdentityError('خروجی معتبر فاز ۱۰.۴.۷ لازم است')
    if extraction.get('active_bank_write') is not False or extraction.get('legal_authenticity_verified') is not False:
        raise LegalIdentityError('ورودی باید صراحتاً قرنطینه و فاقد تأیید حقوقی باشد')
    if not extraction.get('source_pdf_sha256') or not re.fullmatch(r'[0-9a-fA-F]{64}', str(extraction['source_pdf_sha256'])):
        raise LegalIdentityError('هش SHA-256 سند معتبر نیست')
    if quality is not None and (quality.get('phase') != '10.4.8' or quality.get('source_pdf_sha256') != extraction.get('source_pdf_sha256')):
        raise LegalIdentityError('گزارش کیفیت با سند استخراج‌شده تطبیق ندارد')
    pages = extraction.get('pages')
    if not isinstance(pages, list) or not pages:
        raise LegalIdentityError('صفحات استخراج‌شده موجود نیست')
    text = '\n'.join(str(p.get('selected_text', '')) for p in pages if isinstance(p, dict))
    norm = _norm_digits(text)
    kind, kind_hits = _find_unique(text, DOC_RULES)
    issuer, issuer_hits = _find_unique(text, ISSUERS)
    dates = sorted(set(_norm_digits(m.group(0)).replace('/', '-') for m in _DATE_RE.finditer(norm)))
    numbers = []
    for pattern in _NUMBER_PATTERNS:
        numbers.extend(_norm_digits(m.group(1)).strip() for m in pattern.finditer(norm))
    numbers = sorted(set(n for n in numbers if n))
    # Ambiguous or multiple candidates are intentionally not resolved by guesswork.
    official_number = numbers[0] if len(numbers) == 1 else None
    document_date = dates[0] if len(dates) == 1 else None
    ambiguity = []
    if len({k for k, _ in [(k, t) for k, terms in DOC_RULES for t in terms if t in text]}) > 1:
        ambiguity.append('multiple_document_kind_signals')
    if len({k for k, _ in [(k, t) for k, terms in ISSUERS for t in terms if t in text]}) > 1:
        ambiguity.append('multiple_issuer_signals')
    if len(dates) > 1: ambiguity.append('multiple_date_candidates')
    if len(numbers) > 1: ambiguity.append('multiple_official_number_candidates')
    if not extraction.get('complete'): ambiguity.append('extraction_incomplete')
    if quality and quality.get('review_required'): ambiguity.append('extraction_quality_review_required')
    fields = {'kind': kind, 'issuer': issuer, 'official_number': official_number, 'date': document_date}
    missing = [k for k, v in fields.items() if not v]
    identity = None
    if not missing and not ambiguity:
        identity_material = '|'.join(['IR', issuer or '', kind or '', official_number or '', document_date or ''])
        identity = 'IR-' + hashlib.sha256(identity_material.encode('utf-8')).hexdigest()[:24]
    confidence = 0.0
    if kind: confidence += 0.30
    if issuer: confidence += 0.25
    if official_number: confidence += 0.20
    if document_date: confidence += 0.15
    if extraction.get('complete'): confidence += 0.10
    if ambiguity: confidence = min(confidence, 0.59)
    return {
        'phase': '10.4.9', 'source_pdf_sha256': extraction['source_pdf_sha256'],
        'source_url': extraction.get('source_url'), 'proposed_document_kind': kind,
        'document_kind_evidence': kind_hits, 'proposed_issuer': issuer,
        'issuer_evidence': issuer_hits, 'proposed_official_number': official_number,
        'official_number_candidates': numbers, 'proposed_document_date': document_date,
        'date_candidates': dates, 'identity_fields_missing': missing,
        'ambiguity_flags': ambiguity, 'machine_confidence_score': round(confidence, 2),
        'stable_document_id_proposal': identity,
        'identity_status': 'candidate_identity_generated' if identity else 'identity_incomplete_or_ambiguous',
        'legal_authenticity_verified': False, 'legal_status_verified': False,
        'human_review_required': True, 'active_bank_write': False,
        'decision': 'quarantine_metadata_proposal_only',
        'generated_at': datetime.now(timezone.utc).isoformat(),
    }

def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='Offline legal identity proposal for quarantined Dotic extraction')
    p.add_argument('--input', required=True); p.add_argument('--quality-report'); p.add_argument('--output')
    a = p.parse_args(argv)
    extraction = json.loads(Path(a.input).read_text(encoding='utf-8'))
    quality = json.loads(Path(a.quality_report).read_text(encoding='utf-8')) if a.quality_report else None
    result = classify_extraction(extraction, quality)
    out = Path(a.output) if a.output else Path(a.input).with_name(Path(a.input).stem + '.identity.json')
    out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'output': str(out), 'identity_status': result['identity_status'], 'human_review_required': True}, ensure_ascii=False))
    return 0
if __name__ == '__main__': raise SystemExit(main())
