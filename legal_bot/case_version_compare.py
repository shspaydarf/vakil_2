"""Deterministic structural comparison for case versions.

The module deliberately stays local/extractive.  It does not decide the legal
importance or effect of a change; it surfaces structured differences that are
usually easy to miss in a plain line diff, while preserving exact source text.
"""
from __future__ import annotations

import re
import difflib
from collections import defaultdict
from typing import Any

from .analysis import analyze
from .text_guard import normalize_output


_DIGIT_TRANS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')


def _norm(value: Any) -> str:
    s = str(value or '')
    s = s.translate(_DIGIT_TRANS)
    s = s.replace('ي', 'ی').replace('ى', 'ی').replace('ك', 'ک')
    s = s.replace('\u200c', ' ').replace('\u200f', ' ').replace('\u200e', ' ')
    s = re.sub(r'[ـ]+', '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def _key(value: Any) -> str:
    s = _norm(value).lower()
    s = re.sub(r'[«»"“”\'،؛,:.()\[\]{}]+', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def _clip(text: str, n: int = 520) -> str:
    text = re.sub(r'\s+', ' ', str(text or '')).strip()
    if len(text) <= n:
        return text
    return text[:n].rsplit(' ', 1)[0] + '…'


def _unique(values, limit=30):
    out = []
    seen = set()
    for value in values:
        k = _key(value)
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(str(value).strip())
        if len(out) >= limit:
            break
    return out


def _sentences(text: str):
    # Keep OCR/newline boundaries meaningful.  We intentionally do not attempt
    # grammatical sentence reconstruction because that can merge clauses.
    chunks = re.split(r'(?<=[.!؟؛])\s+|[\r\n]+', text or '')
    return [re.sub(r'\s+', ' ', x).strip(' -•▪◦') for x in chunks if len(x.strip()) >= 20]


def _comparison_chunks(text: str, min_chars: int = 8):
    """Shorter chunks for scalar fields where a whole sentence may be tiny."""
    chunks = re.split(r'(?<=[.!؟؛])\s+|[\r\n]+', text or '')
    return [re.sub(r'\s+', ' ', x).strip(' -•▪◦') for x in chunks if len(x.strip()) >= min_chars]


def _extract_duration(text: str):
    # Guard word-number alternatives so «دوازده» is never partially captured
    # as «دو» or «ده».
    word_numbers = (
        'صد|نود|هشتاد|هفتاد|شصت|پنجاه|چهل|سی|بیست|نوزده|هجده|هفده|شانزده|پانزده|چهارده|سیزده|دوازده|یازده|ده|نه|هشت|هفت|'
        'شش|پنج|چهار|سه|دو|یک|نیم'
    )
    number = rf'(?:[0-9۰-۹]{{1,4}}|(?<![آ-ی])(?:{word_numbers})(?![آ-ی]))'
    unit = r'(?:روز|روزه|هفته|هفته‌ای|ماه|ماهه|سال|ساله)'
    patterns = [
        rf'(?:مدت|برای مدت|به مدت|ظرف مدت|مهلت|مهلت انجام|مهلت پرداخت|مهلت تسویه)'
        rf'(?:\s+[^،؛.\n]{{0,35}}?)?\s*(?:حداکثر|حداقل|به)?\s*({number}\s*{unit})',
        rf'(?:تا|ظرف)\s*(?:مدت)?\s*({number}\s*{unit})',
        rf'({number}\s*{unit})\s*(?:از تاریخ|پس از|بعد از)',
        rf'({number}\s*{unit})(?=\s*(?:است|باشد|می‌باشد|می باشد|خواهد بود|بود))',
    ]
    out=[]
    for sent in _comparison_chunks(text):
        for pat in patterns:
            for m in re.finditer(pat,sent,re.I):
                out.append({'value':m.group(1),'text':sent})
    return _unique_records(out,'value',30)



def _extract_status(text: str):
    pats = [
        r'(?:پرداخت|تسویه|واریز|تأدیه|تادیه)\s*(?:شده|نشده|گردیده|نگردیده|نشد|شد)',
        r'(?:عدم\s+پرداخت|عدم\s+تسویه|بدهکار|طلبکار|مطالبه\s+نشده|مطالبه\s+شده)',
        r'(?:محکومیت|برائت|محکوم\s+شد|محکوم\s+نشده|حکم\s+به|قرار\s+صادر)',
    ]
    out = []
    for sent in _comparison_chunks(text):
        if any(re.search(p, sent, re.I) for p in pats):
            out.append({'value': sent, 'text': sent})
    return _unique_records(out, 'value', 20)


def _unique_records(rows, field, limit):
    out = []
    seen = set()
    for row in rows:
        k = _key(row.get(field))
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(row)
        if len(out) >= limit:
            break
    return out


def _extract_party_records(text: str):
    """Extract explicit role labels without treating narrative verbs as names."""
    labels=(
        r'خواهان|خوانده|شاکی|مشتکی\s*عنه|متهم|موکل|کارفرما|پیمانکار|فروشنده|خریدار|'
        r'موجر|مستأجر|مستاجر|متعهدله|متعهد|ضامن|مالک|متصرف|زوج|زوجه|طرف\s*اول|طرف\s*دوم'
    )
    label_re=rf'(?:{labels})'
    pat=re.compile(
        rf'({label_re})\s*[:：\-]\s*(.+?)(?=\s*(?:[.،؛\n]|$)|\s*{label_re}\s*[:：\-])',
        re.I,
    )
    out=[]; seen=set()
    for m in pat.finditer(text or ''):
        role=re.sub(r'\s+',' ',m.group(1)).strip()
        name=re.sub(r'\s+',' ',m.group(2)).strip(' .،؛:-')
        if len(name)<2 or len(name)>100 or len(name.split())>10: continue
        if re.search(r'^(?:تقدیم شد|صادر شد|می[‌ ]?باشد|است|هست|خواهد بود)$',name,re.I): continue
        key=(_key(role),_key(name))
        if key in seen: continue
        seen.add(key); out.append(f'{role}: {name}')
        if len(out)>=30: break
    # Also preserve common «علیه ...» / «به طرفیت ...» identity signals.
    for m in re.finditer(r'(?:علیه|به\s+طرفیت)\s+([^\n،؛.]{2,80})',text or '',re.I):
        name=re.sub(r'\s+',' ',m.group(1)).strip(' .،؛:-')
        if len(name)<2 or len(name)>80: continue
        if re.search(r'\b(?:دادخواست|درخواست|مطالبه|تقدیم|صادر)\b',name,re.I): continue
        value=f'طرف مقابل: {name}'
        k=_key(value)
        if k in seen: continue
        seen.add(k); out.append(value)
        if len(out)>=30: break
    return out


def _guess_document_type_local(text: str):
    t=_norm(text)[:5000]
    rules=[
        ('رأی/دادنامه',r'دادنامه|رأی\s+صادر|حکم\s+به'),
        ('قرارداد',r'قرارداد|طرفین\s+قرارداد|ثمن|موجر|مستأجر|مستاجر'),
        ('دادخواست',r'دادخواست|ریاست\s+محترم|خواسته\s*:'),
        ('لایحه',r'لایحه|در\s+پاسخ\s+به'),
        ('اظهارنامه',r'اظهارنامه|مخاطب'),
        ('اجرائیه',r'اجرائیه|اجرای\s+احکام'),
    ]
    for label,pat in rules:
        if re.search(pat,t,re.I): return label
    return ''


def _extract_money_records(text: str, analyzed_rows):
    """Extract money with or without currency when nearby money cues exist."""
    rows=[{'value':x.get('value',''),'context':x.get('context','')} for x in analyzed_rows if x.get('value')]
    pat=re.compile(
        r'(?<![0-9۰-۹])([0-9۰-۹][0-9۰-۹,،.\s]{0,24})'
        r'(?:\s*(میلیون|میلیارد|هزار))?\s*(تومان|ریال)?(?![آ-ی])',re.I)
    cue=re.compile(r'مبلغ|ثمن|قیمت|ودیعه|اجرت|حق\s*الزحمه|پیش\s*پرداخت|پیش‌پرداخت|وجه|خسارت|بدهی|طلب|پرداخت|تومان|ریال|میلیون|میلیارد',re.I)
    for sent in _comparison_chunks(text):
        for m in pat.finditer(sent):
            raw=re.sub(r'\s+',' ',m.group(0)).strip(' ،,')
            if not raw or not re.search(r'[0-9۰-۹]',raw): continue
            before=sent[max(0,m.start()-70):m.start()]
            after=sent[m.end():m.end()+30]
            local_before=sent[max(0,m.start()-25):m.start()]
            local_after=sent[m.end():m.end()+25]
            # Date/identifier fragments such as ۱۴۰۴/۰۱/۰۱ must never become
            # money merely because the same sentence also contains «مبلغ».
            if '/' in sent[max(0,m.start()-2):m.end()+2] or '-' in sent[max(0,m.start()-2):m.end()+2]:
                continue
            if not (m.group(2) or m.group(3) or cue.search(local_before) or cue.search(local_after)): continue
            if not m.group(2) and not m.group(3) and not cue.search(local_before): continue
            rows.append({'value':raw,'context':before[-80:]})
    out=[]; seen=set()
    for row in rows:
        k=_key(row['value'])
        if not k or k in seen: continue
        seen.add(k); out.append(row)
    return out[:40]


def _extract_clause_refs(text: str):
    pats=[
        r'(?:بند|بندِ)\s*[0-9۰-۹]+(?:\s*[الف-ی])?',
        r'(?:تبصره)\s*[0-9۰-۹]+',
        r'(?:ماده|مواد)\s*[0-9۰-۹]+(?:\s*(?:و|تا)\s*[0-9۰-۹]+)?',
    ]
    out=[]; seen=set()
    for pat in pats:
        for m in re.finditer(pat,text or '',re.I):
            v=re.sub(r'\s+',' ',m.group(0)).strip(); k=_key(v)
            if k and k not in seen:
                seen.add(k); out.append(v)
            if len(out)>=40: return out
    return out


def _extract_amount_records(text: str, analyzed_rows):
    return _extract_money_records(text, analyzed_rows)




def _extract_sensitive_local(text: str):
    groups={
        'حق فسخ':r'حق\s+فسخ|خیار\s+فسخ|فسخ\s+قرارداد',
        'انفساخ':r'انفساخ|منفسخ',
        'اسقاط خیارات':r'اسقاط\s+خیارات|اسقاط\s+کافه\s+خیارات|خیارات.*اسقاط',
        'وجه التزام':r'وجه\s+التزام|خسارت\s+تأخیر',
        'شرط داوری':r'شرط\s+داوری|داوری|داور',
        'ضمان/وثیقه':r'ضمانت|ضامن|وثیقه|رهن|تضمین',
        'اقرار/اسقاط حق':r'اقرار|اسقاط\s+حق|صرف\s*نظر|رضایت\s+قطعی',
        'محرمانگی':r'محرمانگی|محرمانه|عدم\s+افشا',
        'عدم انتقال/محدودیت':r'عدم\s+انتقال|عدم\s+واگذاری|عدم\s+رقابت',
        'اجرا/توقیف':r'اجرائیه|اجرای\s+احکام|توقیف|تأمین\s+خواسته',
        'مرجع رسیدگی':r'دادگاه|شعبه|شورای\s+حل\s+اختلاف|داوری|دیوان',
    }
    out=[]; seen=set()
    for chunk in _comparison_chunks(text):
        for label,pat in groups.items():
            if re.search(pat,chunk,re.I):
                key=(label,_key(chunk))
                if key in seen: continue
                seen.add(key); out.append((label,chunk[:700]))
    return out[:60]


def _unique_sensitive(rows):
    out=[]; seen=set()
    for label,text in rows:
        k=(str(label).strip(),_key(text))
        if not k[0] or not k[1] or k in seen: continue
        seen.add(k); out.append((k[0],str(text).strip()))
    return out[:60]



def _extract_court_refs_local(text: str):
    pats=[
        r'دادگاه\s+[^\n،؛.]{3,80}',
        r'شعبه\s+(?:[0-9۰-۹]+|اول|دوم|سوم|چهارم|پنجم|ششم|هفتم|هشتم|نهم|دهم)\s*[^\n،؛.]{0,60}',
        r'(?:کلاسه|شماره\s+پرونده|پرونده)\s*[:：]?\s*[^\n،؛.]{3,50}',
        r'دیوان\s+(?:عالی|عدالت)\s*[^\n،؛.]{0,50}',
        r'شورای\s+حل\s+اختلاف\s*[^\n،؛.]{0,50}',
        r'اجرای\s+احکام\s*[^\n،؛.]{0,50}',
    ]
    out=[]; seen=set()
    for pat in pats:
        for m in re.finditer(pat,text or '',re.I):
            v=re.sub(r'\s+',' ',m.group(0)).strip(' .،؛:-')
            k=_key(v)
            if len(v)>=5 and k not in seen:
                seen.add(k); out.append(v)
            if len(out)>=30: return out
    return out


def _extract_short_field(text: str, patterns, limit=20):
    out=[]; seen=set()
    for chunk in _comparison_chunks(text):
        if not any(re.search(p,chunk,re.I) for p in patterns): continue
        k=_key(chunk)
        if k and k not in seen:
            seen.add(k); out.append(chunk[:700])
        if len(out)>=limit: break
    return out


def _analysis_snapshot(text: str) -> dict:
    data=analyze(text or '')
    parties=_unique(_extract_party_records(text),30)
    evidence=[
        x.get('text','') for x in (data.get('evidence') or [])
        if x.get('text') and re.search(r'(?:شهادت|گواه|کارشناس|تأمین\s*دلیل|معاینه\s*محل|سند(?:\s+رسمی|\s+عادی)?|رسید|پیامک|فیلم|تصویر|پرینت|حساب|شبا|فیش|اقرار|اظهارنامه|ابلاغ|ثنا)',str(x.get('text')),re.I)
    ]
    claims=_unique([x.get('claim','') for x in (data.get('claims') or []) if x.get('claim')] + _extract_short_field(text,[r'خواهان|خوانده|شاکی|مطالبه|درخواست|تقاضا|اعتراض|دفاع|محکومیت|الزام|ابطال|فسخ|تخلیه|استرداد'],20),20)
    obligations=_unique([x.get('text','') for x in (data.get('obligations') or []) if x.get('text')] + _extract_short_field(text,[r'متعهد|مکلف|ملزم|باید|عهده.?دار|مسئول\s+پرداخت'],20),20)
    remedies=_unique([x.get('text','') for x in (data.get('remedies') or []) if x.get('text')] + _extract_short_field(text,[r'محکومیت|الزام|استرداد|تخلیه|تحویل|ابطال|تنفیذ|توقف|توقیف|اعسار|تقسیط|اجرائیه|جبران\s+خسارت|نفقه|مهریه|اجرت'],20),20)
    courts=_unique([x.get('value','') for x in (data.get('courts') or []) if x.get('value')] + _extract_court_refs_local(text),30)
    statuses=_unique([x.get('value','') for x in _extract_status(text)] + _extract_short_field(text,[r'(?:پرداخت|تسویه|واریز|تأدیه|تادیه)\s*(?:شده|نشده|گردید|نگردید|شد|نشد|است|نیست|انجام)',r'محکومیت|برائت|محکوم\s+شد|حکم|قرار|دادنامه|رأی|اجرائیه|توقیف'],20),20)
    return {
        'document_type':data.get('document_type') or _guess_document_type_local(text),
        'parties':parties,
        'amounts':_extract_amount_records(text,data.get('amounts') or []),
        'dates':[x.get('value','') for x in (data.get('dates') or []) if x.get('value')],
        'claims':claims,
        'obligations':obligations,
        'legal_references':[x.get('reference','') for x in (data.get('legal_references') or []) if x.get('reference')],
        'clause_refs':_extract_clause_refs(text),
        'remedies':remedies,
        'sensitive':_unique_sensitive([(x.get('label',''),x.get('text','')) for x in (data.get('sensitive_clauses') or []) if x.get('text')] + _extract_sensitive_local(text)),
        'courts':courts,
        'evidence':evidence,
        'durations':_extract_duration(text),
        'statuses':[{'value':x,'text':x} for x in statuses],
    }



def _set_diff(old_values, new_values):
    old = {_key(x): x for x in old_values if _key(x)}
    new = {_key(x): x for x in new_values if _key(x)}
    return [old[k] for k in old.keys() - new.keys()], [new[k] for k in new.keys() - old.keys()]


def _fuzzy_changes(old_values, new_values, threshold=0.48, max_pairs=8):
    """Pair likely changed sentences so a changed clause is not shown as two unrelated items."""
    old = [x for x in old_values if _key(x)]
    new = [x for x in new_values if _key(x)]
    used = set(); pairs = []
    for ov in old:
        best = None
        ok = _key(ov)
        for idx, nv in enumerate(new):
            if idx in used:
                continue
            nk = _key(nv)
            if not nk or ok == nk:
                continue
            score = difflib.SequenceMatcher(a=ok, b=nk, autojunk=False).ratio()
            if best is None or score > best[0]:
                best = (score, idx, nv)
        if best and best[0] >= threshold:
            used.add(best[1])
            pairs.append((ov, best[2], best[0]))
            if len(pairs) >= max_pairs:
                break
    return pairs


def _compare_field_exact(label, old_values, new_values, limit=8):
    removed, added = _set_diff(old_values, new_values)
    return {'label': label, 'removed': removed[:limit], 'added': added[:limit], 'changed': []}


def _compare_field(label, old_values, new_values, limit=8):
    removed, added = _set_diff(old_values, new_values)
    pairs = _fuzzy_changes(removed, added, max_pairs=min(6, limit))
    paired_old = {_key(x[0]) for x in pairs}
    paired_new = {_key(x[1]) for x in pairs}
    return {
        'label': label,
        'removed': [x for x in removed if _key(x) not in paired_old][:limit],
        'added': [x for x in added if _key(x) not in paired_new][:limit],
        'changed': pairs,
    }


def _compare_sensitive(old_rows, new_rows):
    old = defaultdict(list); new = defaultdict(list)
    for label, text in old_rows:
        old[label].append(text)
    for label, text in new_rows:
        new[label].append(text)
    out = []
    for label in sorted(set(old) | set(new)):
        diff = _compare_field(label, old[label], new[label], limit=5)
        if diff['removed'] or diff['added'] or diff['changed']:
            diff['label'] = label
            out.append(diff)
    return out


def _text_diff(old_text: str, new_text: str, max_blocks=10):
    old_lines = [re.sub(r'\s+', ' ', x).strip() for x in (old_text or '').splitlines() if x.strip()]
    new_lines = [re.sub(r'\s+', ' ', x).strip() for x in (new_text or '').splitlines() if x.strip()]
    sm = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    blocks = []
    total = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            continue
        total += 1
        if len(blocks) < max_blocks:
            blocks.append((tag, '\n'.join(old_lines[i1:i2]), '\n'.join(new_lines[j1:j2])))
    return blocks, len(old_lines), len(new_lines), total


def _render_field(diff):
    lines = []
    for old, new, score in diff.get('changed') or []:
        lines.append(f"🔁 {diff['label']} تغییر کرده")
        lines.append(f"   قبلی: «{_clip(old, 360)}»")
        lines.append(f"   جدید: «{_clip(new, 360)}»")
    for value in diff.get('removed') or []:
        lines.append(f"➖ {diff['label']} حذف/دیگر دیده نشد: «{_clip(value, 360)}»")
    for value in diff.get('added') or []:
        lines.append(f"➕ {diff['label']} اضافه/جدید دیده شد: «{_clip(value, 360)}»")
    return lines


def _compare_amounts(old_rows, new_rows, limit=8):
    """Pair amounts by nearby wording, not by arbitrary numeric order."""
    old = [x for x in old_rows if x.get('value')]
    new = [x for x in new_rows if x.get('value')]
    used = set(); changed=[]; old_unmatched=[]
    for row in old:
        best=None
        context=_key(row.get('context'))
        for idx,nrow in enumerate(new):
            if idx in used:
                continue
            ncontext=_key(nrow.get('context'))
            score=difflib.SequenceMatcher(a=context, b=ncontext, autojunk=False).ratio() if context and ncontext else 0.0
            # Same amount wording gets a strong pairing even if the number changed.
            if context and ncontext and any(tok in ncontext for tok in context.split()[:3] if len(tok) >= 3):
                score += 0.18
            if best is None or score > best[0]:
                best=(score, idx, nrow)
        if best and best[0] >= 0.52:
            used.add(best[1])
            if _key(row['value']) != _key(best[2]['value']):
                changed.append((row['value'], best[2]['value'], best[0]))
        else:
            old_unmatched.append(row['value'])
    new_unmatched=[row['value'] for idx,row in enumerate(new) if idx not in used]
    return {'label':'مبالغ', 'removed':old_unmatched[:limit], 'added':new_unmatched[:limit], 'changed':changed[:limit]}


def compare_case_versions(base_text: str, new_text: str) -> dict:
    """Return structured + textual comparison without external services."""
    base_text = base_text or ''
    new_text = new_text or ''
    old = _analysis_snapshot(base_text)
    new = _analysis_snapshot(new_text)

    fields = [
        _compare_field('طرفین/اشخاص', old['parties'], new['parties']),
        _compare_amounts(old['amounts'], new['amounts']),
        _compare_field('تاریخ‌ها', old['dates'], new['dates']),
        _compare_field('مدت/مهلت', [x['value'] for x in old['durations']], [x['value'] for x in new['durations']]),
        _compare_field('خواسته/ادعا', old['claims'], new['claims']),
        _compare_field('تعهدات', old['obligations'], new['obligations']),
        _compare_field('مراجع قانونی', old['legal_references'], new['legal_references']),
        _compare_field('بندها/تبصره‌ها/مواد', old['clause_refs'], new['clause_refs']),
        _compare_field('نوع سند', [old['document_type']] if old['document_type'] else [], [new['document_type']] if new['document_type'] else []),
        _compare_field('خواسته/اثر', old['remedies'], new['remedies']),
        _compare_field('مرجع/شناسه پرونده', old['courts'], new['courts']),
        _compare_field('وضعیت پرداخت/رأی', [x['value'] for x in old['statuses']], [x['value'] for x in new['statuses']]),
        _compare_field_exact('ادله/مستندات', old['evidence'], new['evidence'], limit=5),
    ]
    sensitive = _compare_sensitive(old['sensitive'], new['sensitive'])
    blocks, old_n, new_n, total_blocks = _text_diff(base_text, new_text)

    changed_fields = [x for x in fields if x['removed'] or x['added'] or x['changed']]
    structural_count = sum(len(x['removed']) + len(x['added']) + len(x['changed']) for x in changed_fields)
    sensitive_count = sum(len(x['removed']) + len(x['added']) + len(x['changed']) for x in sensitive)

    lines = [
        '🔎 گزارش مقایسه نسخه جدید با پرونده اصلی',
        '',
        f"📊 خلاصه: {structural_count} تغییر ساختاری قابل استخراج | {sensitive_count} مورد در بندهای حساس | {total_blocks} بلوک تغییر متنی",
        '',
        'این گزارش با استخراج محلی و قطعی ساخته شده است. «پیدا نشدن» یا «تغییر» در این گزارش به‌تنهایی اثر حقوقی تغییر را تعیین نمی‌کند؛ متن دقیق نسخه‌ها مبنای بررسی است.',
        '',
    ]

    if old['document_type'] or new['document_type']:
        lines.append(f"📄 نوع سند: اصلی «{old['document_type'] or 'نامشخص'}» | جدید «{new['document_type'] or 'نامشخص'}»")
        if old['document_type'] != new['document_type']:
            lines.append('   ℹ️ نوع سندِ استخراج‌شده بین دو نسخه متفاوت تشخیص داده شده؛ این فقط یک تشخیص متنی است.')
        lines.append('')

    if changed_fields:
        lines.append('🧩 تغییرات ساختاری قابل استخراج')
        for field in changed_fields:
            lines.extend(_render_field(field))
        lines.append('')
    else:
        lines.extend(['🧩 در فیلدهای ساختاری قابل استخراج تفاوتی پیدا نشد.', ''])

    if sensitive:
        lines.append('⚖️ بندها و موضوعات حساسِ تغییرکرده')
        for item in sensitive[:12]:
            label = item['label']
            for oldv, newv, _ in item.get('changed') or []:
                lines.append(f"🔁 {label}: متن بند تغییر کرده")
                lines.append(f"   قبلی: «{_clip(oldv, 330)}»")
                lines.append(f"   جدید: «{_clip(newv, 330)}»")
            for value in item.get('removed') or []:
                lines.append(f"➖ {label}: «{_clip(value, 330)}»")
            for value in item.get('added') or []:
                lines.append(f"➕ {label}: «{_clip(value, 330)}»")
        lines.append('')

    lines.append('📝 تفاوت متنی دقیق')
    lines.append(f'خطوط متن اصلی: {old_n} | خطوط نسخه جدید: {new_n}')
    if not blocks:
        lines.append('تفاوت متنی قابل تشخیصی پیدا نشد.')
    else:
        for i, (tag, removed, added) in enumerate(blocks, 1):
            label = {'replace': '✏️ تغییر', 'delete': '➖ حذف از نسخه جدید', 'insert': '➕ اضافه‌شده در نسخه جدید'}.get(tag, '✏️ تغییر')
            lines.append(f'{label} — مورد {i}')
            if removed:
                lines.append('نسخه اصلی: «' + _clip(removed) + '»')
            if added:
                lines.append('نسخه جدید: «' + _clip(added) + '»')
        if total_blocks > len(blocks):
            lines.append(f'ℹ️ {total_blocks - len(blocks)} بلوک تغییر متنی دیگر هم وجود دارد که برای کوتاه ماندن پیام نمایش داده نشد.')

    lines.append('')
    lines.append('📌 برای بازبینی سریع، ابتدا مبلغ، تاریخ/مهلت، طرفین، خواسته/تعهدات، بندهای حساس و مراجع قانونی بالا را با اصل سند تطبیق دهید.')

    return {
        'old': old,
        'new': new,
        'fields': fields,
        'sensitive': sensitive,
        'text_blocks': blocks,
        'text_block_count': total_blocks,
        'structural_change_count': structural_count,
        'sensitive_change_count': sensitive_count,
        'report': normalize_output('\n'.join(lines)),
    }
