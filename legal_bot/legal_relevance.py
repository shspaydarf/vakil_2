"""Local-first matching of source case passages to potentially related law articles.

This module deliberately avoids legal conclusions. It only maps a short source
passage to law records already present in the bundled legal corpus.
"""
import re
from collections import Counter
from .laws import LEGAL_CORPUS, clean_legal_text, norm
from .important_terms import matching_phrases

MAX_RESULTS = 10
MIN_SCORE = 7

SUBJECT_FAMILIES = {
    'قرارداد': ('قانون مدنی','قانون الزام به ثبت رسمی معاملات اموال غیرمنقول','قانون پیش‌فروش ساختمان','بسته کاربردی قانون تجارت الکترونیکی'),
    'ملک': ('قانون ثبت اسناد و املاک','قانون الزام به ثبت رسمی معاملات اموال غیرمنقول','قانون مدنی','بسته کاربردی قانون شهرداری (مواد کلیدی)','بسته کاربردی قانون افراز و فروش املاک مشاع'),
    'چک': ('قانون صدور چک','قانون تجارت','بسته عملی چک برگشتی کیفری و حقوقی'),
    'سفته': ('قانون تجارت',),
    'کار': ('قانون کار','قانون تأمین اجتماعی','آیین‌نامه اجرایی قانون بیمه بیکاری','بسته عملی مراجع حل اختلاف کار (هیأت تشخیص و حل اختلاف)'),
    'خانواده': ('قانون حمایت خانواده','قانون مدنی','بسته کاربردی تحولات مهریه و محکومیت مالی (طرح/مصوبات ۱۴۰۴)'),
    'طلاق': ('قانون حمایت خانواده','قانون مدنی'),
    'مهریه': ('قانون حمایت خانواده','قانون مدنی','قانون نحوه اجرای محکومیت‌های مالی','بسته کاربردی تحولات مهریه و محکومیت مالی (طرح/مصوبات ۱۴۰۴)','بسته عملی مهریه عندالمطالبه و عندالاستطاعه'),
    'اجاره': ('قانون روابط موجر و مستأجر ۱۳۷۶','قانون ساماندهی بازار زمین، مسکن و اجاره بها مصوب ۱۴۰۳','بسته کاربردی قانون ساماندهی بازار زمین، مسکن و اجاره بها ۱۴۰۳','بسته کاربردی سقف افزایش اجاره و شکایت مستأجر'),
    'تخلیه': ('قانون روابط موجر و مستأجر ۱۳۷۶','بسته عملی دستور تخلیه فوری'),
    'شهرداری': ('بسته کاربردی قانون شهرداری (مواد کلیدی)','بسته عملی اعتراض به رأی کمیسیون ماده ۱۰۰ شهرداری','بسته عملی اعتراض به رأی کمیسیون ماده ۷۷ عوارض'),
    'تصادف': ('قانون بیمه اجباری خسارات وارد شده به شخص ثالث','قانون مجازات اسلامی','بسته کاربردی قانون بیمه'),
    'کیفری': ('قانون مجازات اسلامی','قانون آیین دادرسی کیفری','قانون کاهش مجازات حبس تعزیری مصوب ۱۳۹۹'),
    'جرم': ('قانون مجازات اسلامی','قانون آیین دادرسی کیفری','قانون کاهش مجازات حبس تعزیری مصوب ۱۳۹۹'),
    'دادخواست': ('قانون آیین دادرسی مدنی',),
    'تجدیدنظر': ('قانون آیین دادرسی مدنی','قانون آیین دادرسی کیفری'),
    'شورا': ('قانون شوراهای حل اختلاف مصوب ۱۴۰۲','آیین‌نامه اجرایی قانون شوراهای حل اختلاف مصوب ۱۴۰۳'),
    'اعسار': ('قانون نحوه اجرای محکومیت‌های مالی','آیین‌نامه نحوه اجرای محکومیت‌های مالی مصوب ۱۳۹۹','بسته عملی مستثنیات دین و اعسار'),
    'استخدام': ('بسته کاربردی قانون مدیریت خدمات کشوری (استخدام)','قانون مدیریت خدمات کشوری'),
}

CASE_FAMILY_TRIGGERS = {
    'خانواده': ('طلاق','زوج','زوجه','مهریه','نکاح','نکاحیه','حضانت','تمکین','اجرت‌المثل','نفقه','فسخ نکاح'),
    'قرارداد': ('قرارداد','متعهد','متعهدله','فسخ قرارداد','وجه التزام','شرط ضمن عقد'),
    'ملک': ('ملک','زمین','آپارتمان','عرصه','اعیان','سند مالکیت','ثبتی','افراز','مشاع'),
    'چک': ('چک','گواهی عدم پرداخت','صیاد'),
    'سفته': ('سفته',),
    'کار': ('کارگر','کارفرما','حقوق و دستمزد','بیمه کار','اخراج','بیمه بیکاری'),
    'اجاره': ('اجاره','مستأجر','موجر','تخلیه','ودیعه','اجاره‌بها','سقف اجاره'),
    'تخلیه': ('تخلیه','مستأجر','موجر'),
    'شهرداری': ('شهرداری','کمیسیون ماده ۱۰۰','ماده ۱۰۰','عوارض','پروانه ساختمانی','تغییر کاربری'),
    'تصادف': ('تصادف','حادثه رانندگی','خودرو','شخص ثالث','دیه مصدومیت'),
    'کیفری': ('جرم','متهم','شاکی','مشتکی‌عنه','کیفری','سرقت','کلاهبرداری','ضرب و جرح'),
    'دادرسی': ('دادخواست','ابلاغ','تجدیدنظر','فرجام','واخواهی','صلاحیت دادگاه'),
    'شورا': ('شورای حل اختلاف','شورا','سازش','گزارش اصلاحی'),
    'اعسار': ('اعسار','تقسیط','مستثنیات دین','محکوم‌به'),
    'استخدام': ('استخدام','پیمانی','رسمی','تبدیل وضعیت','کارمند'),
}

STOPWORDS = {
    'از','به','در','با','برای','که','این','آن','را','و','یا','اما','اگر','هر','یک',
    'بر','تا','است','شد','شده','شود','می','نیز','هم','عدم','موجب','مورد','درباره',
    'طرف','طرفین','خواهان','خوانده','اعلام','کرده','کردند','بوده','باشد','است','شد','شده','شود','وجود','موجب','درخواست','مبلغ','پرداخت','وجه','معامله','مقرر','قانون','ماده','مواد','مندرج','مذکور','حسب','مطابق','وفق','نامبرده',
}


def _tokens(text):
    s = norm(clean_legal_text(text))
    return [t for t in re.findall(r'[\wآ-ی]+', s) if len(t) >= 3 and t not in STOPWORDS]


# Document frequency gives rare legal words more weight than generic words such as «پرداخت» or «مبلغ».
# V140: case relevance consumes exactly the same legal corpus as ordinary
# legal search. Source type remains metadata for display/ranking only.
SOURCE_INDEX = LEGAL_CORPUS

_DOC_FREQ = Counter()
_TOTAL_DOCS = max(1, len(SOURCE_INDEX))
for _law in SOURCE_INDEX:
    _DOC_FREQ.update(set(_tokens(_law.get('clean_text') or _law.get('text') or '')))

def _idf(token):
    import math
    return math.log((_TOTAL_DOCS + 1) / (_DOC_FREQ.get(token, 0) + 1)) + 1

for _law in SOURCE_INDEX:
    _law['_tokens']=Counter(_tokens(_law.get('clean_text') or _law.get('text') or ''))


def _sentences(text):
    # Newlines are meaningful in OCR/PDF output; punctuation is a secondary boundary.
    out=[]
    for raw in re.split(r'(?<=[.!؟؛])\s+|[\r\n]+', str(text or '')):
        s=re.sub(r'\s+',' ',raw).strip(' -•▪◦')
        if len(s) >= 45:
            out.append(s[:700])
    return out


def _pages(text):
    matches=list(re.finditer(r'\[صفحه\s+(\d+)\]', str(text or '')))
    if not matches:
        return [(None,str(text or ''))]
    out=[]
    for i,m in enumerate(matches):
        end=matches[i+1].start() if i+1<len(matches) else len(str(text or ''))
        body=str(text or '')[m.end():end].strip()
        if body: out.append((int(m.group(1)),body))
    return out


def _source_passages(text, limit=28):
    result=[]; seen=set()
    for page, body in _pages(text):
        for sent in _sentences(body):
            key=norm(sent)
            if key in seen: continue
            seen.add(key)
            result.append({'text':sent,'page':page})
            if len(result)>=limit: return result
    return result


def _score(passage, law):
    pt=passage.get('_tokens') or Counter(_tokens(passage['text']))
    lt=law.get('_tokens') or Counter(_tokens(law.get('clean_text') or law.get('text') or ''))
    if not pt or not lt: return 0, []
    common=set(pt) & set(lt)
    score=0.0
    matched=[]
    for t in common:
        score += min(pt[t],2) * min(lt[t],3) * min(6.0,_idf(t))
        matched.append(t)
    phrase_hits=[]
    law_text=norm(law.get('clean_text') or law.get('text') or '')
    for phrase in (passage.get('_phrases') or [])[:20]:
        p=norm(phrase)
        if len(p)>=5 and p in law_text:
            score += 10 + min(len(p.split()),4)
            phrase_hits.append(phrase)
    # A relationship should contain at least one informative overlap.
    informative=[t for t in common if len(t)>=5 and _idf(t)>=1.25]
    if not informative and not phrase_hits:
        return 0, []
    if len(common) >= 4: score += 3
    if len(common) >= 7: score += 3
    title=norm(law.get('law',''))
    # Topic-family boost keeps a contract passage from drifting into unrelated
    # regulations merely because generic words occur in both records.
    pnorm=norm(passage['text'])
    family=None
    for family_name, triggers in CASE_FAMILY_TRIGGERS.items():
        if any(norm(t) in pnorm for t in triggers):
            family=SUBJECT_FAMILIES.get(family_name)
            break
    # Strong semantic gate: once a passage clearly belongs to a case family,
    # unrelated statutes are rejected rather than merely receiving a small penalty.
    if family:
        # The title-based family gate is for statute/regulation records.
        # Rulings and advisory opinions have institution titles rather than a
        # subject-law title, so they must be judged by their own text.
        if law.get('kind','law') == 'law' and law.get('law') not in family:
            return 0, []
        if informative:
            score += 8 if law.get('kind','law') == 'law' else 0
        if law.get('kind','law') != 'law' and len(informative) < 3 and not phrase_hits:
            return 0, []
    else:
        # Generic words such as «استفاده»، «محل»، «دارایی» are too common to
        # establish a legal relationship by themselves. Require two informative
        # overlaps unless an explicit multi-word legal phrase matched.
        if len(informative) < 2 and not phrase_hits:
            return 0, []
    return int(score), sorted(set(matched), key=lambda x:(-len(x),x))[:8] + phrase_hits[:4]


def _simple_excerpt(text, max_chars=300):
    """A short, source-faithful explanation; never invents a legal rule."""
    s=clean_legal_text(text)
    s=re.sub(r'\s+',' ',s).strip()
    # Keep at most two source clauses/sentences. This is intentionally labelled
    # as a short summary, not a generated legal interpretation.
    parts=[p.strip() for p in re.split(r'(?<=[.!؟؛])\s+|(?<=:)\s+',s) if p.strip()]
    chosen=' '.join(parts[:2]) if parts else s
    return chosen[:max_chars].rstrip(' ،؛,') + ('…' if len(chosen)>max_chars else '')


def _reason(passage, matched):
    if matched:
        return 'این بخش از متن پرونده با موضوعات و عبارات موجود در این ماده هم‌پوشانی متنی دارد.'
    return 'این بخش از متن پرونده از نظر موضوعی با این ماده هم‌پوشانی احتمالی دارد.'


def find_relevant_laws(text, limit=MAX_RESULTS, max_sources_per_passage=3):
    """Return up to ``limit`` distinct source passages, each with up to 3 sources.

    A passage is the unit shown to the user. Several legal sources may legitimately
    relate to the same passage. The limits are ceilings, not targets: weak matches
    are never added just to fill a quota.
    """
    limit=max(1,min(int(limit or MAX_RESULTS),MAX_RESULTS))
    max_sources_per_passage=max(1,min(int(max_sources_per_passage or 3),3))
    passages=_source_passages(text)
    for p in passages:
        p['_tokens']=Counter(_tokens(p['text']))
        p['_phrases']=matching_phrases(p['text'])
    candidates=[]
    for pidx,p in enumerate(passages):
        for source in SOURCE_INDEX:
            score, matched=_score(p,source)
            if score < MIN_SCORE:
                continue
            candidates.append((score, len(matched), pidx, p, source, matched))
    best_by_source={}
    for item in candidates:
        key=(item[4].get('kind','law'), item[4].get('law',''), item[4].get('article',''),
             item[4].get('ruling_number',''), item[4].get('consultation_number',''))
        if key not in best_by_source or (item[0],item[1]) > (best_by_source[key][0],best_by_source[key][1]):
            best_by_source[key]=item
    groups={}
    for item in best_by_source.values():
        groups.setdefault(item[2], []).append(item)
    ranked_groups=[]
    for pidx,items in groups.items():
        items.sort(key=lambda x:(-x[0],-x[1],x[4].get('kind','law'),x[4].get('law',''),x[4].get('article','')))
        top=items[:max_sources_per_passage]
        group_score=top[0][0] + (min(top[1][0],top[0][0])*0.20 if len(top)>1 else 0)
        ranked_groups.append((group_score, top[0][0], pidx, top))
    ranked_groups.sort(key=lambda x:(-x[0],-x[1],x[2]))
    out=[]
    for _,_,_,items in ranked_groups[:limit]:
        passage=items[0][3]
        sources=[]
        for score, _, _, _, source, matched in items:
            kind=source.get('kind','law')
            if kind == 'ruling':
                court = source.get('court_type')
                prefix = 'رأی دیوان عدالت اداری' if court == 'diwan_adalat' else 'رأی وحدت رویه'
                label=f"{prefix} شماره {source.get('ruling_number') or source.get('article','')}"
            elif kind == 'consultation':
                label=f"نظریه مشورتی شماره {source.get('consultation_number') or source.get('article','')}"
            elif kind == 'sample':
                label=f"نمونه/متن کاربردی: {source.get('law','') or source.get('title','')}"
            elif kind == 'circular':
                label=f"بخشنامه: {source.get('law','') or source.get('title','')}"
            else:
                article=source.get('article','')
                label=f"{source.get('law','')} — ماده {article}" if article else source.get('law','')
            sources.append({
                'score':score, 'kind':kind, 'law':source.get('law',''), 'article':source.get('article',''),
                'title':source.get('title',''), 'display_label':label,
                'text':source.get('text') or source.get('clean_text',''), 'clean_text':source.get('clean_text',''),
                'source_status':source.get('source_status'), 'verification_label':source.get('verification_label'),
                'source_urls':source.get('source_urls',[]), 'reason':_reason(passage,matched),
                'explanation':_simple_excerpt(source.get('clean_text') or source.get('text','')),
                'matched_terms':matched,
            })
        out.append({'passage':passage['text'], 'page':passage.get('page'), 'sources':sources})
    return out
