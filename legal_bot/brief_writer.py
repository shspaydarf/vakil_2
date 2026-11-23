# -*- coding: utf-8 -*-
"""Deterministic, local-first Persian legal brief writer.

No external AI is required. It builds a conservative draft from user-supplied
facts, stored case text, and locally indexed legal sources. It never invents
case facts or legal citations.
"""
import re
from typing import Iterable, Dict, List

try:
    from .brief_templates import TEMPLATES, TEMPLATE_PROFILES, TEMPLATE_WRITING_PROFILES
except Exception:
    TEMPLATES, TEMPLATE_PROFILES = {}, {}


def _clean(s):
    return re.sub(r'\s+', ' ', str(s or '')).strip()


def _sentences(text: str) -> List[str]:
    parts = re.split(r'(?<=[\.!؟!؛])\s+|\n+', text or '')
    out = []
    try:
        from .source_quality import source_segment_ok
    except Exception:
        source_segment_ok = None
    for p in parts:
        p = _clean(p)
        if len(p) < 20 or p in out:
            continue
        if source_segment_ok is not None and not source_segment_ok(p, min_chars=20):
            continue
        out.append(p)
    return out


def _pick_sentences(text: str, keywords: Iterable[str], limit=6):
    ss = _sentences(text)
    hits = []
    for s in ss:
        if any(k in s for k in keywords):
            hits.append(s)
        if len(hits) >= limit:
            break
    # If keyword hits are thin, fill with early substantive sentences.
    if len(hits) < min(3, limit):
        for s in ss:
            if s not in hits:
                hits.append(s)
            if len(hits) >= limit:
                break
    return hits[:limit]


def _facts_summary(facts, limit=10):
    return _sentences(facts)[:limit]


def _source_lines(sources):
    out = []
    seen = set()
    for i, x in enumerate(sources or [], 1):
        if not isinstance(x, dict):
            continue
        key = _source_key(x)
        if key in seen:
            continue
        seen.add(key)
        title = _clean(x.get('law') or x.get('title') or x.get('name') or 'منبع حقوقی')
        art = _clean(x.get('article') or x.get('ruling_number') or x.get('ماده') or '')
        text = _clean(x.get('text') or x.get('clean_text') or '')
        if not text:
            continue
        label = f'{title}' + (f' — {art}' if art else '')
        cid = _clean((x.get('citation') or {}).get('id') or '')
        out.append((f'[S{i}]', label, text[:1200], cid))
    return out[:10]


def _issue_candidates(combined, brief_type='', template_key=None):
    """Extract substantive issue statements without turning every fact into an issue."""
    base_keys = [
        'فسخ', 'انفساخ', 'بطلان', 'وجه التزام', 'خسارت', 'الزام', 'محکومیت',
        'اعسار', 'تقسیط', 'تخلیه', 'ابطال', 'تنفیذ', 'مطالبه', 'صلاحیت',
        'داوری', 'چک', 'سفته', 'مهریه', 'نفقه', 'حضانت', 'تجدیدنظر',
        'اعتراض', 'پرداخت', 'عدم پرداخت', 'گواهی عدم پرداخت', 'اجرائیه',
        'ودیعه', 'اجاره', 'دادنامه', 'رأی'
    ]
    profile = TEMPLATE_PROFILES.get(template_key or {}, {}) if isinstance(template_key, str) else {}
    keys = list(dict.fromkeys(base_keys + list(profile.get('keywords', []))))
    hits = _pick_sentences(combined, keys, 12)
    out=[]
    for h in hits:
        # Avoid treating simple metadata sentences (amount/date/number) as a
        # legal issue unless they also contain a substantive legal term.
        matched = [k for k in keys if k in h]
        if not matched:
            continue
        if len(matched) == 1 and matched[0] in {'پرداخت', 'مطالبه', 'مبلغ', 'تاریخ'} and len(h) < 80:
            continue
        if h not in out:
            out.append(h)
    if 'تجدیدنظر' in (brief_type or '') and not any('رأی' in x or 'دادنامه' in x for x in out):
        out.append('آیا رأی/دادنامه مورد اعتراض از حیث استدلال، استناد یا انطباق با محتویات پرونده ایراد قابل طرح دارد؟')
    return out[:8]


def _evidence_matrix(bits, evidence_sentences, issues):
    rows=[]
    raw=[]
    for e in bits.get('evidence') or []:
        t=e.get('text') if isinstance(e,dict) else e
        if t: raw.append(_clean(t))
    raw += evidence_sentences
    seen=set()
    for ev in raw:
        if ev in seen: continue
        seen.add(ev)
        related=[]
        for idx,issue in enumerate(issues,1):
            terms=[w for w in re.findall(r'[؀-ۿ]{4,}', issue) if w not in {'آیا','مورد','استدلال'}]
            if any(t in ev for t in terms[:5]): related.append(str(idx))
        rows.append((ev, related))
        if len(rows)>=8: break
    return rows


def _argument_plan(issues, source_pack, evidence_rows):
    out=[]
    for i,issue in enumerate(issues[:6],1):
        ev=[ev for ev,rels in evidence_rows if str(i) in rels]
        src=source_pack[min(i-1,len(source_pack)-1)] if source_pack else None
        line=f'مسئله {i}: {issue}'
        out.append((line, ev[:2], src[0] if src else ''))
    return out


def _type_profile(brief_type: str) -> Dict:
    t = brief_type or ''
    if 'تجدیدنظر' in t:
        return {
            'greeting': 'ریاست محترم دادگاه تجدیدنظر',
            'intro': 'احتراماً، نسبت به دادنامه/رأی صادره، لایحه تجدیدنظرخواهی به شرح زیر تقدیم می‌شود:',
            'request_hint': 'نقض/اصلاح دادنامه و اتخاذ تصمیم شایسته',
            'focus': ['رأی', 'دادنامه', 'تجدیدنظر', 'خطا', 'نقض', 'مستندات'],
        }
    if 'پاسخ' in t:
        return {
            'greeting': 'ریاست محترم مرجع قضایی مربوط',
            'intro': 'احتراماً، در پاسخ به لایحه/اظهارات طرف مقابل، مطالب زیر تقدیم می‌شود:',
            'request_hint': 'رد ادعاهای فاقد دلیل طرف مقابل و اتخاذ تصمیم شایسته',
            'focus': ['پاسخ', 'دفاع', 'رد', 'اظهار', 'لایحه طرف'],
        }
    if 'اعتراض' in t or 'درخواست' in t:
        return {
            'greeting': 'ریاست محترم مرجع صالح',
            'intro': 'احتراماً، اعتراض/درخواست به شرح زیر جهت بررسی تقدیم می‌شود:',
            'request_hint': 'پذیرش درخواست/اعتراض و صدور دستور مقتضی',
            'focus': ['اعتراض', 'درخواست', 'دستور', 'قرار', 'اجرائیه'],
        }
    return {
        'greeting': 'ریاست محترم مرجع قضایی مربوط',
        'intro': 'احتراماً، در خصوص موضوع مطروحه، مطالب زیر جهت بررسی و اتخاذ تصمیم شایسته تقدیم می‌شود:',
        'request_hint': 'صدور حکم شایسته وفق مقررات و مستندات',
        'focus': ['دفاع', 'خواسته', 'ادعا', 'مطالبه'],
    }


def _analyze_bits(case_text: str) -> Dict:
    """Optional richer extraction when case text is available."""
    out = {
        'parties': [], 'claims': [], 'amounts': [], 'dates': [],
        'evidence': [], 'remedies': [], 'courts': [], 'overview': [],
        'document_type': '',
    }
    if not case_text or len(case_text) < 80:
        return out
    try:
        from .analysis import analyze
        r = analyze(case_text)
        out['parties'] = r.get('parties') or []
        out['claims'] = r.get('claims') or []
        out['amounts'] = r.get('amounts') or []
        out['dates'] = r.get('dates') or []
        out['evidence'] = r.get('evidence') or []
        out['remedies'] = r.get('remedies') or []
        out['courts'] = r.get('courts') or []
        out['overview'] = r.get('overview') or []
        out['document_type'] = r.get('document_type') or ''
    except Exception:
        pass
    return out


def _template_context(template_key: str, combined: str):
    profile = TEMPLATE_PROFILES.get(template_key or '', {})
    if not profile:
        return None
    low = combined or ''
    present = []
    missing = []
    for item in profile.get('required', []):
        # Required labels are intentionally broad; absence means "ask/review",
        # not that the fact is false.
        if any(k in low for k in [item, item.replace('/', ' '), item.replace(' ', '')]):
            present.append(item)
        else:
            missing.append(item)
    keyword_hits = [k for k in profile.get('keywords', []) if k in low]
    return {
        'sections': profile.get('sections', []),
        'required': profile.get('required', []),
        'present': present,
        'missing': missing,
        'keyword_hits': keyword_hits,
        'title': TEMPLATES.get(template_key, {}).get('title', ''),
    }


def _source_relevance(source, combined: str, issues):
    title = _clean(source.get('law') or source.get('title') or source.get('name') or '')
    text = _clean(source.get('text') or source.get('clean_text') or '')
    hay = f'{title} {text}'
    terms = set(re.findall(r'[؀-ۿ]{4,}', combined or ''))
    issue_terms = set()
    for issue in issues[:8]:
        issue_terms.update(re.findall(r'[؀-ۿ]{4,}', issue))
    hits = sorted((terms | issue_terms) & set(re.findall(r'[؀-ۿ]{4,}', hay)), key=len, reverse=True)
    return hits[:4]


def _consistency_checks(combined: str, bits: Dict):
    checks=[]
    amounts = re.findall(r'(?:\d[\d۰-۹]*(?:[,.]\d[\d۰-۹]*)*)\\s*(?:میلیون|میلیارد|هزار)?\\s*(?:تومان|ریال)', combined or '')
    if len(set(amounts)) > 1:
        checks.append('چند مبلغ متفاوت در متن دیده شد؛ مشخص کنید هر مبلغ مربوط به کدام ادعا/مرحله است.')
    dates = re.findall(r'(?:13|14)\d{2}[/-][0-9۰-۹]{1,2}[/-][0-9۰-۹]{1,2}', combined or '')
    if len(set(dates)) >= 3:
        checks.append('چند تاریخ مهم در متن وجود دارد؛ رابطه زمانی قرارداد، سررسید، مطالبه و ابلاغ را قبل از نهایی‌سازی کنترل کنید.')
    if re.search(r'(پرداخت شد|پرداخت گردید|تسویه شد)', combined) and re.search(r'(پرداخت نشده|عدم پرداخت|بدهکار)', combined):
        checks.append('عباراتی با ظاهر متعارض درباره پرداخت/عدم پرداخت دیده شد؛ قبل از درج در لایحه روشن شود کدام ادعا صحیح است.')
    if bits.get('parties') and len(bits.get('parties')) >= 2:
        roles = [str(x.get('role','')) for x in bits['parties'] if isinstance(x,dict)]
        if roles and len(set(roles)) == 1:
            checks.append('نقش طرفین در استخراج اولیه یکسان یا نامشخص دیده می‌شود؛ نام و نقش هر طرف کنترل شود.')
    return checks


def _template_adaptation(template_key: str, combined: str, issues, sources):
    ctx = _template_context(template_key, combined)
    if not ctx:
        return []
    lines=['📦 ساختار قالب منتخب: ' + ctx['title']]
    lines.append('• قالب به‌عنوان اسکلت تنظیم استفاده شده و جایگزین تطبیق حقوقی نیست.')
    for i,sec in enumerate(ctx['sections'],1):
        lines.append(f'{i}. {sec}')
    if ctx['missing']:
        lines.append('⚠️ موارد اختصاصی قالب که در متن ورودی پیدا نشد:')
        lines += [f'• {x}' for x in ctx['missing']]
    if issues:
        lines.append('🔎 مسائل مرتبط با قالب:')
        lines += [f'• {x}' for x in issues[:5]]
    if sources:
        lines.append('📚 تطبیق اولیه منابع با موضوعات:')
        for i,src in enumerate(sources[:8],1):
            hits=_source_relevance(src,combined,issues)
            label=_clean(src.get('law') or src.get('title') or src.get('name') or 'منبع حقوقی')
            lines.append(f'• S{i}: {label}' + (f' — کلیدواژه‌های مشترک: {"، ".join(hits)}' if hits else ' — ارتباط متنی مشخص نیست'))
    return lines


def _template_section_keywords(template_key: str):
    return {
        'mahr_claim': {
            'رابطه زوجیت و سند نکاحیه':['سند نکاحیه','ازدواج','زوج','زوجه'],
            'میزان و وضعیت مهریه':['مهریه','مبلغ','عندالمطالبه','عندالاستطاعه'],
            'پرداخت/عدم پرداخت':['پرداخت','عدم پرداخت','تسویه'],
            'دلایل و منضمات':['سند','رسید','مدرک','پیوست'],
            'خواسته':['خواسته','مطالبه','تقاضا'],
        },
        'esar': {
            'مبنای محکومیت':['دادنامه','اجرائیه','محکوم‌به','محکوم به'],
            'وضعیت مالی':['اعسار','توان مالی','وضعیت مالی'],
            'درآمد و هزینه‌های ضروری':['درآمد','هزینه','مخارج'],
            'اموال و دیون':['اموال','دارایی','دین','بدهی'],
            'دلایل اعسار':['استشهادیه','شاهد','گردش حساب','مدرک'],
            'تقاضای تقسیط':['تقسیط','قسط','اقساط','درخواست'],
        },
        'check_claim': {
            'مشخصات چک':['چک','شماره','تاریخ','مبلغ','بانک'],
            'گواهی عدم پرداخت':['گواهی عدم پرداخت','عدم پرداخت'],
            'مبنای دین':['قرارداد','تعهد','دین','معامله'],
            'دلایل':['سند','رسید','گواهی','مدرک'],
            'خسارت تأخیر':['خسارت تأخیر','تاخیر','تأخیر'],
            'خواسته':['خواسته','مطالبه','تقاضا'],
        },
        'check_defense': {
            'مشخصات چک':['چک','شماره','تاریخ','مبلغ'],
            'ادعای خواهان':['خواهان','مطالبه','ادعا'],
            'دفاع اصلی':['دفاع','پرداخت','جعل','ایراد','عدم تحویل'],
            'دلایل دفاع':['رسید','واریز','قرارداد','مکاتبات','مدرک'],
            'ایرادات قابل بررسی':['ایراد','جعل','پرداخت','قرارداد'],
            'خواسته':['خواسته','رد دعوا','تقاضا'],
        },
        'rent_evict': {
            'سمت و مشخصات ملک':['مالک','سمت','ملک','پلاک','نشانی'],
            'قرارداد اجاره':['قرارداد اجاره','اجاره','موجر','مستأجر'],
            'مدت اجاره':['مدت','تاریخ','سررسید','انقضا'],
            'جهت تخلیه':['تخلیه','عدم پرداخت','پایان مدت'],
            'اجور معوق':['اجور','اجاره‌بها','اجاره بها','معوق'],
            'دلایل':['قرارداد','اظهارنامه','رسید','سند'],
            'خواسته':['خواسته','تخلیه','مطالبه'],
        },
        'tenant_defense': {
            'رابطه استیجاری':['اجاره','قرارداد','موجر','مستأجر'],
            'موضع مستأجر':['دفاع','اعتراض','موضع'],
            'پرداخت‌ها و ودیعه':['پرداخت','ودیعه','رهن','رسید'],
            'ایرادات':['ایراد','اعتراض'],
            'دلایل':['قرارداد','رسید','مدرک','اظهارنامه'],
            'خواسته':['خواسته','استرداد','رد'],
        },
        'delay_damage': {
            'منشأ دین':['دین','قرارداد','چک','حکم','تعهد'],
            'مبلغ و تاریخ سررسید':['مبلغ','تاریخ','سررسید'],
            'مطالبه و عدم پرداخت':['مطالبه','عدم پرداخت','اظهارنامه'],
            'دوره تأخیر':['دوره','تأخیر','تاخیر','تاریخ'],
            'دلایل':['سند','مدرک','اظهارنامه','حکم'],
            'خواسته':['خواسته','خسارت','تقاضا'],
        },
        'objection_exec': {
            'مشخصات پرونده اجرایی':['پرونده اجرایی','اجرائیه','شماره'],
            'عملیات مورد اعتراض':['عملیات اجرایی','توقیف','مزایده','اجرائیه'],
            'جهت اعتراض':['اعتراض','پرداخت','محاسبه','تأمین'],
            'دلایل':['سند','رسید','مدرک'],
            'فوریت/درخواست موقت در صورت وجود':['فوریت','توقف','دستور موقت'],
            'خواسته':['خواسته','تقاضا','توقف','رفع'],
        },
    }.get(template_key, {})


def _render_template_draft(template_key, combined, bits, sources):
    """Render a template-specific narrative scaffold without inventing facts."""
    profile = TEMPLATE_PROFILES.get(template_key or '', {})
    sections = profile.get('sections') or []
    if not sections:
        return []
    kwmap = _template_section_keywords(template_key)
    writing = TEMPLATE_WRITING_PROFILES.get(template_key, {})
    sentences = _sentences(combined)
    lines = ['✍️ متن پیشنهادی تخصصی بر اساس قالب منتخب', '']
    if writing.get('opening'):
        lines.append(writing['opening'])
        lines.append('')
    used = set()
    for idx, sec in enumerate(sections, 1):
        kws = kwmap.get(sec, [sec])
        hits = []
        for sent in sentences:
            if sent in used:
                continue
            if any(k in sent for k in kws):
                hits.append(sent)
                used.add(sent)
            if len(hits) >= 4:
                break
        lines.append(f'{idx}. {sec}')
        if writing.get('section_intro'):
            lines.append('   ' + writing['section_intro'].format(section=sec))
        if hits:
            # Narrative paragraph: preserve source sentences rather than
            # fabricating legal prose around them.
            lines.append('   ' + ' '.join(hits))
        else:
            lines.append('   [اطلاعات کافی برای این بخش در ورودی پیدا نشد؛ تکمیل دستی لازم است.]')

        matched_sources = []
        for src in sources or []:
            hay = _clean(src.get('law') or src.get('title') or src.get('name') or '') + ' ' + _clean(src.get('text') or src.get('clean_text') or '')
            if any(k in hay for k in kws):
                cid = _clean((src.get('citation') or {}).get('id') or '')
                label = _clean(src.get('law') or src.get('title') or src.get('name') or 'منبع حقوقی')
                art = _clean(src.get('article') or src.get('ruling_number') or src.get('ماده') or '')
                matched_sources.append(f'{label}' + (f' — {art}' if art else '') + (f' [#{cid}]' if cid else ''))
            if len(matched_sources) >= 2:
                break
        if matched_sources:
            lines.append('   منابع انتخاب‌شده مرتبط: ' + '؛ '.join(matched_sources))
        lines.append('')

    if writing.get('request'):
        lines.append('📌 نکته تنظیم خواسته: ' + writing['request'])
        lines.append('')
    lines.append('⚠️ این متن اسکلت تخصصی و پیش‌نویس است؛ واقعیت، دلیل، استناد یا نتیجه حقوقی جدیدی خارج از ورودی و منابع انتخاب‌شده به آن اضافه نشده است.')
    return lines


def _source_key(src):
    return (_clean(src.get('kind') or 'law'), _clean(src.get('citation',{}).get('id') if isinstance(src.get('citation'),dict) else ''), _clean(src.get('law') or src.get('title') or src.get('name')), _clean(src.get('article') or src.get('ruling_number') or src.get('ماده')))


def build_brief(facts, brief_type='لایحه دفاعیه', stage='دادگاه بدوی', sources=None,
                case_text='', mode='new', template_key=None):
    facts = _clean(facts)
    case_text = case_text or ''
    if not facts and not case_text.strip():
        raise ValueError('اطلاعات لازم برای تنظیم لایحه وارد نشده است.')

    combined = (case_text + '\n' + facts).strip()
    profile = _type_profile(brief_type)
    bits = _analyze_bits(case_text)

    party_kw = ['خواهان', 'خوانده', 'شاکی', 'مشتکی', 'موکل', 'طرف مقابل', 'ادعا', 'مطالبه', 'زوجه', 'زوج', 'موجر', 'مستأجر']
    date_kw = ['تاریخ', 'مورخ', 'روز', 'سررسید', 'ابلاغ', 'مهلت']
    amount_kw = ['مبلغ', 'تومان', 'ریال', 'وجه', 'خسارت', 'دیه', 'مهریه', 'نفقه', 'اجاره']
    sens_kw = ['فسخ', 'انفساخ', 'بطلان', 'وجه التزام', 'داوری', 'ضمان', 'رهن', 'چک', 'سفته', 'اقرار', 'اسقاط', 'شرط', 'اعسار', 'تقسیط', 'تخلیه']
    evidence_kw = ['شهادت', 'کارشناس', 'سند', 'رسید', 'پیامک', 'اظهارنامه', 'گواهی', 'معاینه', 'تأمین دلیل']
    request_kw = ['تقاضا', 'خواسته', 'درخواست', 'محکومیت', 'الزام', 'استرداد', 'ابطال', 'تنفیذ', 'تخلیه', 'اعسار']

    party_claims = _pick_sentences(combined, party_kw + profile['focus'], 8)
    dates = _pick_sentences(combined, date_kw, 6)
    amounts = _pick_sentences(combined, amount_kw, 6)
    sensitive = _pick_sentences(combined, sens_kw, 8)
    evidence = _pick_sentences(combined, evidence_kw, 6)
    requests = _pick_sentences(combined, request_kw, 6)

    refs = re.findall(r'(?:ماده|مواد|اصل)\s*[۰-۹0-9]+(?:\s*(?:و|تا)\s*[۰-۹0-9]+)?', combined)
    refs = list(dict.fromkeys(refs))[:15]
    source_pack = _source_lines(sources)
    template_info = _template_context(template_key, combined)
    consistency = _consistency_checks(combined, bits)

    title = brief_type
    if mode == 'edit':
        title += ' — ویرایش و تنظیم مجدد'

    lines = []
    lines += [f'📝 {title}', '', f'مرجع رسیدگی (اعلامی): {stage or "نامشخص"}', '']
    if bits.get('document_type'):
        lines += [f'نوع سند مبنا (برآورد از متن): {bits["document_type"]}', '']
    lines += [profile['greeting'], 'با سلام و احترام', '']
    lines += ['موضوع: ' + brief_type, '']
    lines += [profile['intro'], '']

    n = 1
    # Overview from analyzer
    if bits.get('overview'):
        lines.append(f'{n}) نمای کلی استخراج‌شده از پرونده')
        for x in bits['overview'][:6]:
            lines.append(f'• {x}')
        lines.append('')
        n += 1

    lines.append(f'{n}) شرح مختصر موضوع و وقایع')
    fact_items = _facts_summary(facts, 10)
    if case_text:
        for s in _facts_summary(case_text, 12):
            if s not in fact_items:
                fact_items.append(s)
            if len(fact_items) >= 12:
                break
    if fact_items:
        lines += [f'• {s}' for s in fact_items[:12]]
    else:
        lines.append('• اطلاعات تکمیلی پرونده بر اساس متن ارائه‌شده قابل درج است.')
    lines.append('')
    n += 1

    # Parties
    if bits.get('parties'):
        lines.append(f'{n}) طرفین منعکس‌شده در متن')
        for p in bits['parties'][:8]:
            role = _clean(p.get('role') or '')
            name = _clean(p.get('name') or '')
            lines.append(f'• {role}: {name}'.strip(': '))
        lines.append('')
        n += 1

    if party_claims:
        lines.append(f'{n}) مواضع و ادعاهای منعکس‌شده در مستندات')
        lines += [f'• {s}' for s in party_claims[:8]]
        lines.append('')
        n += 1

    if amounts or bits.get('amounts'):
        lines.append(f'{n}) مبالغ و تعهدات مالی منعکس‌شده')
        if bits.get('amounts'):
            for a in bits['amounts'][:8]:
                v = a.get('value') if isinstance(a, dict) else a
                if v:
                    lines.append(f'• {v}')
        lines += [f'• {s}' for s in amounts[:6]]
        lines.append('')
        n += 1

    if dates or bits.get('dates'):
        lines.append(f'{n}) تاریخ‌ها و وقایع زمانی مهم')
        if bits.get('dates'):
            for d in bits['dates'][:8]:
                v = d.get('value') if isinstance(d, dict) else d
                if v:
                    lines.append(f'• {v}')
        lines += [f'• {s}' for s in dates[:6]]
        lines.append('')
        n += 1

    if evidence or bits.get('evidence'):
        lines.append(f'{n}) اشارات دلیلی و مستنداتی که در متن آمده')
        if bits.get('evidence'):
            for e in bits['evidence'][:6]:
                t = e.get('text') if isinstance(e, dict) else e
                if t:
                    lines.append(f'• {t}')
        lines += [f'• {s}' for s in evidence[:6]]
        lines.append('• اصالت و تأثیر هر دلیل باید جداگانه توسط وکیل ارزیابی شود.')
        lines.append('')
        n += 1

    issues = _issue_candidates(combined, brief_type, template_key)
    evidence_rows = _evidence_matrix(bits, evidence, issues)
    if issues:
        lines.append(f'{n}) مسائل حقوقی قابل بررسی (بدون اعلام نتیجه قطعی)')
        for i, issue in enumerate(issues[:8], 1):
            lines.append(f'• مسئله {i}: {issue}')
        lines.append('')
        n += 1

    if evidence_rows:
        lines.append(f'{n}) ماتریس ادله و ارتباط اولیه با مسائل')
        for ev, rels in evidence_rows:
            tag = '، '.join('مسئله '+r for r in rels) if rels else 'ارتباط مشخص نشده'
            lines.append(f'• دلیل/مستند: {ev[:420]}')
            lines.append(f'  ↳ ارتباط اولیه: {tag}')
        lines.append('• این ارتباط صرفاً استخراج متنی است و ارزش اثباتی دلیل را تعیین نمی‌کند.')
        lines.append('')
        n += 1

    if template_info:
        lines.append(f'{n}) انطباق با قالب منتخب')
        lines += _template_adaptation(template_key, combined, issues, sources)
        lines.append('')
        n += 1

    if consistency:
        lines.append(f'{n}) کنترل سازگاری اطلاعات')
        lines += [f'• {x}' for x in consistency]
        lines.append('')
        n += 1

    if template_info:
        rendered = _render_template_draft(template_key, combined, bits, sources or [])
        if rendered:
            lines.append(f'{n}) متن پیشنهادی ساختاریافته بر اساس قالب')
            lines += rendered
            lines.append('')
            n += 1

    lines.append(f'{n}) دفاعیات و استدلال‌های پیشنهادی (پیش‌نویس)')
    plan = _argument_plan(issues, source_pack, evidence_rows)
    if plan:
        lines.append('• چارچوب استدلال برای تکمیل توسط وکیل:')
        for line, evs, sid in plan[:6]:
            lines.append(f'  – {line}')
            if evs:
                lines.append(f'    ادله مرتبط در متن: {evs[0][:260]}')
            if sid:
                lines.append(f'    منبع قابل تطبیق: {sid}')
        lines.append('• با توجه به عبارات و شروط حساس موجود در مستندات، مفاد مربوط باید در تصمیم‌گیری مورد توجه قرار گیرد:')
        lines += [f'  – {s}' for s in sensitive[:5]]
    lines.append('• دفاع نهایی صرفاً بر مبنای وقایع اثبات‌شده، اسناد موجود و مقررات قابل اعمال تنظیم شود.')
    lines.append('• مواردی که در متن صراحت کافی ندارند نباید به‌عنوان واقعیت قطعی در لایحه نهایی بیاید.')
    if 'تجدیدنظر' in (brief_type or ''):
        lines.append('• جهات تجدیدنظر باید مشخص و مستند به ایرادات رأی و پرونده باشد؛ عبارات کلی به‌تنهایی کافی نیست.')
    lines.append('')
    n += 1

    if refs or source_pack:
        lines.append(f'{n}) مستندات و استنادات قابل تطبیق')
        if refs:
            lines.append('• عبارات ماده‌مانند استخراج‌شده از متن پرونده:')
            lines += [f'  – {r}' for r in refs[:10]]
        if source_pack:
            lines.append('• مواد/منابع بازیابی‌شده از کتابخانه بات (برای تطبیق وکیل، نه استناد خودکار قطعی):')
            for sid, label, text, cid in source_pack[:6]:
                citation_label = f' | {cid}' if cid else ''
                lines.append(f'  {sid} {label}{citation_label}')
                lines.append(f'     {text[:280]}' + ('…' if len(text) > 280 else ''))
        lines.append('')
        n += 1

    lines.append(f'{n}) خواسته / تقاضای پایانی (پیشنهادی بر اساس متن)')
    if bits.get('remedies'):
        for r in bits['remedies'][:5]:
            t = r.get('text') if isinstance(r, dict) else r
            if t:
                lines.append(f'• {t}')
    if requests:
        lines += [f'• {s}' for s in requests[:5]]
    lines.append(f'• تقاضا: {profile["request_hint"]}.')
    lines.append('• جزئیات خواسته باید با دادخواست/پرونده و اراده موکل منطبق شود.')
    lines.append('')
    n += 1

    lines.append(f'{n}) پیوست‌ها (پیشنهادی)')
    lines.append('• تصویر اسناد اصلی و ابلاغیه‌ها')
    lines.append('• هر مدرک پرداخت، کارشناسی، یا مکاتبه مرتبط')
    lines.append('• فهرست پیوست‌ها را در نسخه نهایی دقیق کنید')
    lines.append('')
    lines += ['با احترام', 'وکیل / نماینده قانونی', '']
    lines += [
        '─' * 24,
        '⚠️ این خروجی پیش‌نویس داخلی و استخراجی است؛ استناد، رقم، و نتیجه دعوا را تضمین نمی‌کند.',
        'قبل از تقدیم، تطبیق کامل با پرونده و امضای مسئول پرونده الزامی است.',
    ]
    return '\n'.join(lines)


def review_brief(existing_text, sources=None):
    """Deterministic first-pass review of an existing brief."""
    text = _clean(existing_text)
    if not text:
        raise ValueError('متن لایحه خالی است.')
    checks = []
    if not re.search(r'موضوع\s*[:：]', text):
        checks.append('موضوع لایحه صریح و مستقل درج نشده یا قابل تشخیص نیست.')
    if re.search(r'\.{4,}|……+|\.{3}|_{4,}|نامعلوم|مشخص نیست', text):
        checks.append('جای خالی/نشانه تکمیل‌نشده در متن دیده شد؛ قبل از تقدیم تکمیل شود.')
    if not re.search(r'(ریاست|شعبه|مرجع)', text):
        checks.append('مرجع رسیدگی/خطاب قضایی به‌صورت روشن دیده نمی‌شود.')
    if not re.search(r'(خواسته|تقاضا|درخواست|محکومیت|الزام)', text):
        checks.append('خواسته یا تقاضای نهایی صریحاً قابل تشخیص نیست.')
    if not re.search(r'(ماده\s*[۰-۹0-9]+|اصل\s*[۰-۹0-9]+)', text):
        checks.append('استناد صریح به ماده/اصل در متن پیدا نشد؛ در صورت نیاز از منبع معتبر اضافه شود.')
    if not re.search(r'(پیوست|ضمیمه|سند|مدرک)', text):
        checks.append('بخش مشخصی برای اسناد/پیوست‌ها دیده نمی‌شود.')
    if not re.search(r'(تاریخ|مورخ)', text):
        checks.append('اشاره زمانی/تاریخ در متن کم‌رنگ است.')
    if not re.search(r'(دلیل|شهادت|کارشناس|رسید|سند)', text):
        checks.append('اشاره به ادله در متن کم است؛ در صورت وجود دلیل، ذکر شود.')
    if len(_sentences(text)) < 6:
        checks.append('متن نسبتاً کوتاه است و برای ارزیابی کامل ممکن است به شرح بیشتر نیاز باشد.')
    for phrase in ('قطعاً محکوم خواهد شد', 'حتماً برنده می‌شویم', 'بدون شک', 'صددرصد', 'حکم به نفع قطعی'):
        if phrase in text:
            checks.append(f'عبارت قطعی «{phrase}» نیازمند بازبینی است؛ نتیجه دعوا نباید تضمین شود.')
    issues = _issue_candidates(text)
    if len(issues) == 0:
        checks.append('مسئله/سؤال حقوقی اصلی در متن به‌صورت قابل تشخیص استخراج نشد؛ قبل از نهایی‌سازی مشخص شود.')

    # Local quality-control checks. These are review signals, not findings that
    # a legal statement is false; they never rewrite or delete the user's text.
    # Use a raw split here because _sentences intentionally deduplicates input.
    sentences = [_clean(x) for x in re.split(r'(?<=[.!؟؛])\s+', text) if len(_clean(x)) >= 20]
    normalized = [_clean(x).strip(' .؛،') for x in sentences]
    repeated = []
    frequencies = {}
    for sentence in normalized:
        key = re.sub(r'\s+', ' ', sentence).casefold()
        frequencies[key] = frequencies.get(key, 0) + 1
    repeated = [key for key, count in frequencies.items() if count > 1]
    if repeated:
        checks.append(f'{len(repeated)} جمله تکراری یا تقریباً تکراری شناسایی شد؛ تکرارها را بررسی کنید و فقط در صورت حفظ معنا حذف کنید.')

    vague_authority = re.search(r'(طبق قانون|بر اساس قانون|مطابق مقررات|به موجب قانون|مستنداً به قانون)', text)
    explicit_authority = re.search(r'(ماده\s*[۰-۹0-9]+|اصل\s*[۰-۹۰-۹0-9]+)', text)
    if vague_authority and not explicit_authority:
        checks.append('به قانون/مقررات به‌صورت کلی اشاره شده، اما ماده یا عنوان دقیق منبع به‌وضوح دیده نمی‌شود؛ استناد را فقط پس از راستی‌آزمایی تکمیل کنید.')

    absolute_claims = re.findall(r'[^.!؟\n]{0,100}(?:قطعاً|بدیهی است که|مسلم است که|ثابت است که|بدون تردید)[^.!؟\n]{0,120}', text)
    if absolute_claims:
        checks.append(f'{len(absolute_claims)} عبارت با لحن قطعی پیدا شد؛ بررسی کنید آیا برای هرکدام دلیل مشخص در پرونده وجود دارد.')

    factual_markers = r'(قرارداد|رسید|سند|پیوست|مدرک|شهادت|شاهد|کارشناس|گزارش|صفحه\s*[۰-۹0-9]+|برگ\s*[۰-۹0-9]+|مستندات)'
    assertive_markers = r'(پرداخت|تحویل|ابلاغ|انعقاد|تخلف|عدم انجام|نقض قرارداد|بدهکار|متعهد|توافق|مراجعه|مطالبه)'
    if re.search(assertive_markers, text) and not re.search(factual_markers, text):
        checks.append('متن شامل ادعاهای مربوط به وقایع/تعهدات است، اما نشانه مشخصی از مدرک یا مأخذ آن‌ها پیدا نشد؛ برای هر ادعای مهم، سند یا محل آن را مشخص کنید.')

    # Stage 4: map explicit article/principle mentions to the local source registry.
    # This is traceability metadata only; it does not certify legal validity.
    try:
        from .citation_verifier import audit_citations
        citation_audit = audit_citations(text)
        if citation_audit.get('mentions'):
            needs_manual = [x for x in citation_audit['mentions'] if x.get('verification_level') != 'registry_verified_text_status']
            if needs_manual:
                checks.append(f"{len(needs_manual)} استناد شماره‌دار وضعیت تأیید متن جاری در فهرست پروژه را ندارد یا تطبیق یکتا نشد؛ منبع رسمی و نسخه لازم‌الاجرا را بررسی کنید.")
            else:
                checks.append('عنوان قانون برای استنادهای شماره‌دار در فهرست پروژه تطبیق شد؛ این تطبیق به‌تنهایی صحت شماره ماده یا اعتبار جاری آن را اثبات نمی‌کند.')
    except Exception:
        checks.append('گزارش خودکار فهرست استنادها در دسترس نبود؛ استنادها را دستی با منبع رسمی تطبیق دهید.')

    source_pack = _source_lines(sources)
    consistency = _consistency_checks(text, {})
    if consistency:
        checks += consistency
    lines = ['🔍 بررسی اولیه لایحه', '']
    lines.append('موارد قابل بررسی:')
    if checks:
        lines += [f'• {x}' for x in checks]
    else:
        lines.append('• ایراد ساختاری آشکار در بررسی اولیه پیدا نشد؛ تطبیق حقوقی و factual همچنان ضروری است.')
    lines += ['', '📚 منابع قابل تطبیق در این مرحله:']
    if source_pack:
        lines += [f'• {sid} {label}' + (f' | {cid}' if cid else '') for sid, label, _, cid in source_pack]
    else:
        lines.append('• منبع کافی در بسته بازیابی‌شده نیست؛ استناد جدید از طرف موتور اضافه نمی‌شود.')
    try:
        from .citation_verifier import render_citation_audit
        lines += ['', render_citation_audit(text)]
    except Exception:
        pass
    lines += ['', '⚠️ این گزارش ویرایش حقوقی قطعی نیست؛ کنترل اولیه ساختار و ادعاهای قطعی است.']
    return '\n'.join(lines)


def render_structured_brief(draft: Dict, *, max_facts: int = 20, max_arguments: int = 12) -> str:
    """Render a clean, document-oriented Persian draft from traced data only.

    This is a presentation/editorial pass, not generative legal reasoning: it
    must not add facts, authorities, or conclusions that are absent upstream.
    """
    d = draft or {}
    if not d:
        return 'پیش‌نویس ساختاری در دسترس نیست.'

    def clean(value):
        return _clean(value).strip(' •▪◦-')

    lines = []
    title = clean(d.get('draft_type')) or 'لایحه دفاعیه'
    lines.extend([title, ''])
    cap = d.get('caption') or {}
    if cap.get('court'):
        lines.append(f"مرجع رسیدگی: {clean(cap.get('court'))}")
    if cap.get('parties'):
        lines.append('طرفین: ' + '، '.join(clean(x) for x in cap.get('parties', [])[:8] if clean(x)))
    if cap.get('subject'):
        lines.append(f"موضوع: {clean(cap.get('subject'))}")
    lines.extend(['', 'ریاست محترم مرجع صالح', 'با سلام و احترام،', ''])

    lines.extend(['۱. شرح وقایع و اطلاعات مستند', ''])
    fact_count = 0
    for fact in (d.get('facts') or [])[:max_facts]:
        text = clean(fact.get('text'))
        if not text:
            continue
        source = clean(fact.get('document_name'))
        refs = fact.get('source_refs') or []
        if not source and refs:
            source = f"سند شماره {clean(refs[0])}"
        page = f"، صفحه {fact.get('page')}" if fact.get('page') else ''
        suffix = f" (مأخذ: {source}{page})" if source else ''
        lines.extend([text + suffix, ''])
        fact_count += 1
    if not fact_count:
        lines.extend(['[شرح وقایع مستند باید با مراجعه به پرونده تکمیل شود.]', ''])

    lawyer_inputs = [x for x in (d.get('lawyer_confirmed_inputs') or []) if clean(x.get('value'))]
    if lawyer_inputs:
        lines.extend(['اطلاعات تکمیلی اعلامی وکیل (با منشأ مستقل از اسناد پرونده)', ''])
        for item in lawyer_inputs[:12]:
            label = clean(item.get('label')) or clean(item.get('key')) or 'اطلاعات تکمیلی'
            lines.extend([f"{label}: {clean(item.get('value'))}", 'منشأ: ورودی صریح و تأییدشده وکیل؛ این مقدار مستقلاً با اسناد پرونده راستی‌آزمایی نشده است.', ''])

    lines.extend(['۲. مسائل مورد بررسی', ''])
    issues = [i for i in (d.get('issues') or []) if clean(i.get('label')) or clean(i.get('question'))]
    for idx, issue in enumerate(issues, 1):
        label, question = clean(issue.get('label')), clean(issue.get('question'))
        lines.append(f"{idx}. {label or 'مسئله حقوقی'}" + (f" — {question}" if question and question != label else ''))
    if not issues:
        lines.append('[مسائل حقوقی پرونده هنوز به‌طور ساختاری مشخص نشده‌اند.]')
    lines.append('')

    lines.extend(['۳. دلایل و استدلال‌های قابل تکمیل', ''])
    arguments = (d.get('arguments') or [])[:max_arguments]
    for idx, arg in enumerate(arguments, 1):
        heading = clean(arg.get('heading')) or f'موضوع {idx}'
        lines.extend([f"۳.{idx}. {heading}", ''])
        position = clean(arg.get('position'))
        if position:
            lines.extend([f"مسئله مورد بررسی: {position}", ''])
        for step in arg.get('reasoning_steps') or []:
            text = clean(step.get('text'))
            if not text or step.get('step') == 'application_frame':
                continue
            # Keep strategic framing clearly identified rather than presenting it
            # as a proven fact or a definitive legal conclusion.
            label = 'چارچوب استدلال' if step.get('step') == 'strategy_frame' else 'موضوع'
            lines.extend([f'{label}: {text}', ''])
        for item in arg.get('supporting_evidence') or []:
            claim = clean(item.get('claim_text'))
            status = clean(item.get('status'))
            if claim:
                lines.extend([f"ادعای مرتبط: {claim}" + (f" (وضعیت ثبت‌شده: {status})" if status else ''), ''])
            for evidence in (item.get('evidence') or [])[:4]:
                evidence_text = clean(evidence.get('text'))
                if not evidence_text:
                    continue
                source = clean(evidence.get('document_name')) or 'مدرک پرونده'
                page = f"، صفحه {evidence.get('page')}" if evidence.get('page') else ''
                lines.extend([f"مؤید موجود: {evidence_text} (مأخذ: {source}{page})", ''])
        for authority in (arg.get('authority_refs') or [])[:4]:
            label = clean(authority.get('title')) or 'منبع حقوقی'
            article = clean(authority.get('article_number'))
            citation = clean(authority.get('citation_key'))
            tail = f'، {article}' if article else ''
            tail += f' [{citation}]' if citation else ''
            lines.extend([f'منبع حقوقی ثبت‌شده: {label}{tail}.', ''])
        for gap in (arg.get('missing_support') or [])[:4]:
            message = clean(gap.get('text'))
            if message:
                lines.extend([f'نیازمند تکمیل: {message}', ''])
        lines.extend(['این بخش پیش‌نویس است و پیش از استفاده باید از نظر انطباق با اسناد و قواعد حقوقی بررسی شود.', ''])
    if not arguments:
        lines.extend(['[استدلال اختصاصی کافی در داده‌های ساختاری موجود نیست؛ از افزودن استدلال حدسی خودداری شده است.]', ''])

    lines.extend(['۴. خواسته یا تقاضا', ''])
    relief = [clean(x) for x in (d.get('requested_relief') or [])[:8] if clean(x)]
    if relief:
        lines.extend(relief)
    else:
        lines.append('[خواسته نهایی باید بر اساس پرونده و نظر تنظیم‌کننده تعیین و تأیید شود.]')
    lines.extend(['', '۵. منابع و ارجاعات ثبت‌شده', ''])
    citations = (d.get('citations') or [])
    for citation in citations[:20]:
        label = clean(citation.get('citation_key') or citation.get('article_number') or citation.get('authority_id'))
        text = clean(citation.get('exact_text'))
        location = clean(citation.get('source_location'))
        if label or text:
            row = (f'{label}: ' if label else '') + text[:900]
            if location:
                row += f' (محل منبع: {location})'
            lines.extend([row, ''])
    if not citations:
        lines.extend(['در داده‌های فعلی، منبع تأییدشده‌ای برای درج خودکار ثبت نشده است.', ''])

    gaps = []
    for item in d.get('missing_information') or []:
        value = clean(item.get('text') if isinstance(item, dict) else item)
        if value and value not in gaps:
            gaps.append(value)
    for warning in d.get('warnings') or []:
        if warning.get('type') in {'missing_information', 'authority_review', 'argument_gap', 'requested_relief_missing'}:
            value = clean(warning.get('items') or warning.get('text'))
            if value and value not in gaps:
                gaps.append(value)
    if gaps:
        lines.extend(['موارد نیازمند تکمیل پیش از ارائه', ''])
        lines.extend([f'• {item}' for item in gaps[:12]])
        lines.append('')

    lines.extend(['با احترام،', '[نام و امضای تنظیم‌کننده]', '',
                  'یادآوری: این متن بر پایه داده‌های ثبت‌شده و قابل ردیابی تهیه شده است. نبودن یک داده در این پیش‌نویس به معنای اثبات یا رد آن نیست. پیش از تقدیم، متن، مستندات و استنادهای حقوقی باید توسط وکیل یا تنظیم‌کننده مسئول بررسی و تأیید شوند.'])
    return '\n'.join(lines)

