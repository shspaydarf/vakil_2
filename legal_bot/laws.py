import json, re, os
from .config import LAW_FILE
from .glossary import expand_query
from .knowledge import law_source, verification_label, citation_for_record
from .legal_text_cleanup import cleanup_legal_text

# Search-only normalization. Stored legal text is never rewritten.
def norm(s):
    s = str(s or '').replace('ي','ی').replace('ى','ی').replace('ك','ک').replace('\u200c',' ')
    s = re.sub(r'[\u200e\u200f\ufeff]', '', s)
    return re.sub(r'\s+', ' ', s).strip().lower()

_OCR_REPLACEMENTS = {
    'اسالمی':'اسلامی','ابالغ':'ابلاغ','اعالم':'اعلام','اطالعات':'اطلاعات',
    'اطالع':'اطلاع','اصالح':'اصلاح','اصوال':'اصول','امضاء':'امضا',
    'انحالل':'انحلال','تادیه':'تأدیه','تاسیس':'تأسیس','تامین':'تأمین',
    'تایید':'تأیید','تاثیر':'تأثیر','تعیین':'تعیین','دالئل':'دلایل',
    'راسا':'رأساً','رای':'رأی','معامالت':'معاملات','مسول':'مسئول',
    'مسولیت':'مسئولیت','مسئوليت':'مسئولیت','موسسه':'مؤسسه','موسسات':'مؤسسات',
    'موثر':'مؤثر','هیات':'هیئت','قوه قضائیه':'قوه قضائیه','قضایی':'قضائی',
    'قانوناساسی':'قانون اساسی','دادرسیمدنی':'دادرسی مدنی','دادرسیکیفری':'دادرسی کیفری',
}

def clean_legal_text(text):
    return cleanup_legal_text(text)

with open(LAW_FILE, encoding='utf-8') as f:
    RAW = json.load(f)

# Additional corpus: Supreme Court General Assembly precedent rulings.
RULINGS_FILE = LAW_FILE.parent / 'rulings.json'
try:
    with open(RULINGS_FILE, encoding='utf-8') as f:
        _RULINGS_RAW = json.load(f)
    if isinstance(_RULINGS_RAW, dict):
        _supreme = [dict(x, _court_type='supreme_court') for x in (_RULINGS_RAW.get('rulings') or []) if isinstance(x, dict)]
        _adalat = [dict(x, _court_type='diwan_adalat') for x in (_RULINGS_RAW.get('diwan_adalat_rulings') or []) if isinstance(x, dict)]
        _RULINGS_RAW = _supreme + _adalat
    else:
        _RULINGS_RAW = _RULINGS_RAW
except (FileNotFoundError, json.JSONDecodeError):
    _RULINGS_RAW = []

def _ruling_number_ascii(value):
    return str(value or '').translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩','01234567890123456789'))

RULING_INDEX = []
for item in _RULINGS_RAW:
    if not isinstance(item, dict):
        continue
    text = clean_legal_text(item.get('متن') or item.get('text') or '')
    number = str(item.get('شماره') or item.get('number') or '').strip()
    date = str(item.get('تاریخ') or item.get('date') or '').strip()
    if not number or not text:
        continue
    ref = str(item.get('مرجع') or item.get('مرجع_قضایی') or '').strip()
    is_adalat = item.get('_court_type') == 'diwan_adalat' or 'عدالت' in ref or 'دیوان عدالت' in ref
    court_name = ref or ('هیأت عمومی دیوان عدالت اداری' if is_adalat else 'هیأت عمومی دیوان عالی کشور')
    RULING_INDEX.append({
        'kind': 'ruling',
        'law': court_name,
        'article': number,
        'ruling_number': number,
        'date': date,
        'title': item.get('عنوان') or f'رأی وحدت رویه شماره {number}',
        'text': item.get('متن') or text,
        'clean_text': text,
        'ntext': norm(f"{court_name} رأی وحدت رویه شماره {number} {date} {text}"),
        'source_status': item.get('وضعیت_منبع') or 'user_provided_text',
        'verification_label': item.get('وضعیت_متن') or 'متن فعال پروژه؛ وضعیت تطبیق مستقل باید در استناد نهایی بررسی شود',
        'source_file': item.get('منبع_فایل'),
        'source_files': item.get('منابع_همسان') or [item.get('منبع_فایل')] if item.get('منبع_فایل') else [],
        'court_type': 'diwan_adalat' if is_adalat else 'supreme_court',
    })
    RULING_INDEX[-1]['citation']=citation_for_record(RULING_INDEX[-1])


# Additional corpus: Legal Department advisory opinions supplied by the user.
CONSULTATIONS_FILE = LAW_FILE.parent / 'consultations.json'
try:
    with open(CONSULTATIONS_FILE, encoding='utf-8') as f:
        _CONSULTATIONS_RAW = json.load(f)
    _CONSULTATIONS_RAW = _CONSULTATIONS_RAW.get('consultations', []) if isinstance(_CONSULTATIONS_RAW, dict) else _CONSULTATIONS_RAW
except (FileNotFoundError, json.JSONDecodeError):
    _CONSULTATIONS_RAW = []

CONSULTATION_INDEX = []
for item in _CONSULTATIONS_RAW:
    if not isinstance(item, dict):
        continue
    number = str(item.get('شماره') or item.get('number') or '').strip()
    date = str(item.get('تاریخ') or item.get('date') or '').strip()
    question = clean_legal_text(item.get('سؤال') or item.get('question') or '')
    answer = clean_legal_text(item.get('نظریه') or item.get('answer') or '')
    if not number or not answer:
        continue
    title = f'نظریه مشورتی شماره {number}'
    combined = f'{title} {date} {question} {answer}'
    CONSULTATION_INDEX.append({
        'kind': 'consultation',
        'law': 'نظریات مشورتی اداره کل حقوقی قوه قضاییه',
        'article': number,
        'consultation_number': number,
        'date': date,
        'title': title,
        'question': question,
        'text': answer,
        'clean_text': answer,
        'ntext': norm(combined),
        'source_status': 'user_provided_pdf',
        'verification_label': item.get('وضعیت_متن') or 'استخراج‌شده از PDF ارسالی کاربر',
        'source_file': item.get('منبع_فایل'),
    })
    CONSULTATION_INDEX[-1]['citation']=citation_for_record(CONSULTATION_INDEX[-1])

def search_consultations(q, limit=8):
    q = str(q or '').strip()
    if not q:
        return []
    phrases, terms = _terms(q)
    nq = norm(clean_legal_text(q))
    hits = re.findall(r'(?:نظریه\s*)?(?:مشورتی\s*)?(?:شماره\s*)?([۰-۹0-9]+/[۰-۹0-9]+/[۰-۹0-9]+)', q)
    scored = []
    for x in CONSULTATION_INDEX:
        score = 0
        nt = x['ntext']
        if 'مشورتی' in nq or 'نظریه' in nq:
            score += 20
        if any(_ruling_number_ascii(h) == _ruling_number_ascii(x['consultation_number']) for h in hits):
            score += 100
        if nq and nq in nt:
            score += 20
        for phrase in phrases:
            p = norm(phrase)
            if p and p in nt:
                score += 12
        matched = 0
        for term in terms:
            c = nt.count(term)
            if c:
                matched += 1
                score += min(c, 5) * (3 if len(term) >= 5 else 1)
        if matched >= 2:
            score += 15
        if score:
            scored.append((score, x))
    scored.sort(key=lambda z: (-z[0], _ruling_number_ascii(z[1]['consultation_number'])))
    return [dict(score=s, **x) for s,x in scored[:max(1,min(limit,20))]]

def search_rulings(q, limit=8):
    q = str(q or '').strip()
    if not q:
        return []
    phrases, terms = _terms(q)
    nq = norm(clean_legal_text(q))
    q_ascii = _ruling_number_ascii(q)
    # Explicit ruling number in the query gets a very strong boost.
    number_hits = re.findall(r'(?:رأی\s*)?(?:وحدت\s*رویه\s*)?(?:شماره\s*)?([۰-۹0-9]+(?:/[۰-۹0-9]+)?)', q)
    scored = []
    for x in RULING_INDEX:
        score = 0
        nt = x['ntext']
        if 'وحدت رویه' in nq:
            score += 35
        rn = _ruling_number_ascii(x['ruling_number'])
        if rn and any(_ruling_number_ascii(h) == rn for h in number_hits):
            score += 100
        if nq and nq in nt:
            score += 20
        for phrase in phrases:
            p = norm(phrase)
            if p and p in nt:
                score += 12
        matched_terms = 0
        for term in terms:
            c = nt.count(term)
            if c:
                matched_terms += 1
                score += min(c, 5) * (3 if len(term) >= 5 else 1)
        if matched_terms >= 2:
            score += 18
        if score:
            scored.append((score, x))
    scored.sort(key=lambda z: (-z[0], _ruling_number_ascii(z[1]['ruling_number'])))
    return [dict(score=s, **x) for s,x in scored[:max(1,min(limit,20))]]

# The bundled corpus contains known OCR contamination. Do not expose obviously
# corrupt records to a legal search. This is deliberately conservative:
# a missing result is safer than returning a non-law as a law.
LAW_LIMITS = {
    'قانون مدنی': 1335,
    'قانون تجارت': 600,
    'قانون مجازات اسلامی': 728,
    'قانون حمایت خانواده': 58,
    'قانون صدور چک': 24,
    'قانون آیین دادرسی مدنی': 529,
    'قانون آیین دادرسی کیفری': 648,
    'قانون ثبت اسناد و املاک': 238,
    'قانون نحوه اجرای محکومیت‌های مالی': 29,
    'قانون اساسی جمهوری اسلامی ایران': 177,
}
# V141: fail-closed quarantine gate. Unverified/incomplete law groups are
# stored under data/iran/quarantine/inactive_laws.json and must never enter
# the active search index until a separate source-backed activation review.
QUARANTINED_LAWS = {
    'قانون اساسی جمهوری اسلامی ایران',
    'قانون تأمین اجتماعی',
    'قانون مالیات بر ارزش افزوده',
    'قانون تشکیلات و آیین دادرسی دیوان عدالت اداری',
    'قانون حمایت از حقوق مصرف‌کنندگان',
    'قانون بیمه',
    'قانون حمایت از اطفال و نوجوانان',
    'قانون الزام به ثبت رسمی معاملات اموال غیرمنقول',
    'قانون حمایت از مالکیت صنعتی',
    'قانون کیفیت اخذ پروانه وکالت دادگستری',
    'بسته کاربردی قانون الزام به ثبت رسمی معاملات اموال غیرمنقول',
    'بسته کاربردی آیین‌نامه‌های قانون الزام به ثبت رسمی معاملات اموال غیرمنقول',
    'بسته کاربردی قانون حمایت از اطفال و نوجوانان',
    'بسته کاربردی قانون بیمه',
}

def _article_no(item):
    return str(item.get('number') or item.get('article_no') or item.get('article_number') or item.get('ماده') or item.get('اصل') or '').strip()

def _is_valid_record(title, item):
    if title in QUARANTINED_LAWS:
        return False
    num = _article_no(item)
    text = item.get('text') or item.get('متن') or ''
    if not num or not text or len(clean_legal_text(text)) < 8:
        return False
    limit = LAW_LIMITS.get(title)
    if limit is not None:
        m = re.match(r'(\d+)', num)
        if m and int(m.group(1)) > limit:
            return False
    # Obvious source-footer contamination seen in the supplied corpus.
    bad_markers = ('این قانون که مشتمل بر', 'این قانون که مشتمل است بر')
    if any(x in clean_legal_text(text) for x in bad_markers):
        return False
    return True

INDEX=[]
QUALITY_REPORT={}
for title, articles in RAW.items():
    if str(title).startswith('_') or title in ('metadata',):
        continue
    if not isinstance(articles, list):
        QUALITY_REPORT[title]={'raw':0,'accepted':0,'rejected':0,'note':'skipped_non_list'}
        continue
    accepted=0; rejected=[]
    for item in articles:
        if not isinstance(item,dict):
            rejected.append({'reason':'not_object'})
            continue
        if not _is_valid_record(title,item):
            rejected.append({'article':_article_no(item),'reason':'quarantined_or_invalid'})
            continue
        num=_article_no(item)
        text=item.get('text') or item.get('متن') or ''
        cleaned=clean_legal_text(text)
        src=law_source(title)
        rec={'law':title,'article':num,'text':text,'clean_text':cleaned,
             'ntext':norm(f'{title} {num} {cleaned}'),'source_status': src.get('status','source_pending_import'),
             'verification_label': verification_label(title),
             'source_urls': src.get('known_source_urls',[]),
             'primary_sources': src.get('primary_sources',[]),
             'primary_source_ids': src.get('primary_source_ids',[]),
             'cross_check_urls': src.get('cross_check_urls',[]),
             'last_verified': src.get('last_verified'),
             'activation_note': src.get('activation_note'),
             'kind':'law'}
        rec['citation']=citation_for_record(rec)
        INDEX.append(rec); accepted+=1
    QUALITY_REPORT[title]={'raw':len(articles),'accepted':accepted,'rejected':len(rejected)}
QUALITY_REPORT['_quarantined']=sorted(QUARANTINED_LAWS)

# --- samples & circulars (V108) ---
SAMPLES_FILE = LAW_FILE.parent / 'samples_and_circulars.json'
SAMPLE_INDEX = []
CIRCULAR_INDEX = []
try:
    with open(SAMPLES_FILE, encoding='utf-8') as f:
        _SAMPLES_RAW = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    _SAMPLES_RAW = {}

for item in (_SAMPLES_RAW.get('samples') or []):
    if not isinstance(item, dict):
        continue
    title = str(item.get('عنوان') or '').strip()
    body = str(item.get('شرح_نمونه') or item.get('خواسته') or '').strip()
    if not title or len(body) < 8:
        continue
    cat = str(item.get('دسته') or '')
    court = str(item.get('مرجع_معمول') or '')
    claim = str(item.get('خواسته') or '')
    combined = f"{title} {cat} {court} {claim} {body}"
    rec = {
        'kind': 'sample',
        'law': f'نمونه: {title}',
        'article': cat or 'نمونه',
        'title': title,
        'text': body,
        'clean_text': clean_legal_text(body),
        'ntext': norm(combined),
        'source_status': 'sample_template',
        'verification_label': 'نمونه الگویی آموزشی — جایگزین مشخصات واقعی',
        'category': cat,
        'court': court,
        'claim': claim,
    }
    SAMPLE_INDEX.append(rec)
    INDEX.append(rec)

for item in (_SAMPLES_RAW.get('circulars') or []):
    if not isinstance(item, dict):
        continue
    title = str(item.get('عنوان') or '').strip()
    body = str(item.get('متن') or item.get('موضوع') or '').strip()
    if not title or len(body) < 8:
        continue
    ref = str(item.get('مرجع') or '')
    topic = str(item.get('موضوع') or '')
    combined = f"{title} {ref} {topic} {body}"
    rec = {
        'kind': 'circular',
        'law': f'بخشنامه: {title}',
        'article': 'بخشنامه',
        'title': title,
        'text': body,
        'clean_text': clean_legal_text(body),
        'ntext': norm(combined),
        'source_status': 'circular_summary',
        'verification_label': 'خلاصه عملیاتی بخشنامه/ضابطه',
        'reference': ref,
        'topic': topic,
    }
    CIRCULAR_INDEX.append(rec)
    INDEX.append(rec)

QUALITY_REPORT['_samples'] = len(SAMPLE_INDEX)
QUALITY_REPORT['_circulars'] = len(CIRCULAR_INDEX)

def _terms(q):
    q=norm(clean_legal_text(q))
    # Preserve quoted phrases and also search individual words.
    phrases=re.findall(r'["«](.+?)[»"]',q)
    q_no_quotes=re.sub(r'["«»]',' ',q)
    terms=[x for x in q_no_quotes.split() if len(x)>=2][:12]
    return phrases,terms

# V130: a dependency-free hybrid legal retrieval layer.  It combines exact
# matching, IDF-weighted lexical relevance, glossary expansion, article-number
# matching, source-type intent and deterministic diversity.  It intentionally
# does not claim semantic understanding: without embeddings/reranking service,
# we keep the ranking auditable and reproducible.
_RESEARCH_STOPWORDS={
    'از','به','در','با','برای','که','این','آن','را','و','یا','اما','اگر','هر','یک',
    'بر','تا','است','شد','شده','شود','می','نیز','هم','عدم','موجب','مورد','درباره',
    'طرف','طرفین','خواهان','خوانده','اعلام','کرده','کردند','بوده','باشد','وجود',
    'درخواست','مبلغ','پرداخت','وجه','معامله','مقرر','قانون','ماده','مواد','مندرج',
    'مذکور','حسب','مطابق','وفق','نامبرده','درباره','مربوط','موضوع','خصوص','موردی',
}


def _research_tokens(text):
    s=norm(clean_legal_text(text))
    return [t for t in re.findall(r'[\wآ-ی]+',s) if len(t)>=2 and t not in _RESEARCH_STOPWORDS]


def _research_number(q):
    m=re.search(r'(?:ماده|اصل|بند|تبصره)\s*([0-9۰-۹]+)', norm(q))
    if not m:
        return None
    return m.group(1).translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹','0123456789'))


def _source_intent(q):
    nq=norm(clean_legal_text(q))
    intent=set()
    if any(x in nq for x in ('رأی وحدت رویه','رای وحدت رویه','وحدت رویه')): intent.add('ruling')
    if any(x in nq for x in ('نظریه مشورتی','نظریات مشورتی','نظریه اداره حقوقی')): intent.add('consultation')
    if any(x in nq for x in ('نمونه دادخواست','نمونه لایحه','نمونه اظهارنامه','نمونه شکواییه')): intent.add('sample')
    if any(x in nq for x in ('بخشنامه','دستورالعمل')): intent.add('circular')
    if any(x in nq for x in ('ماده','اصل','قانون')): intent.add('law')
    return intent


def _research_score(query, record, df, total_docs, query_terms, query_phrases, expanded_terms, token_freq=None,
                   query_norm=None, query_number=None, query_intent=None):
    text=record.get('ntext') or norm(record.get('clean_text') or record.get('text') or '')
    # V139-P1: title/article/source intent are query-independent per record/query.
    # Precompute the record title once per process and reuse it across searches.
    title=record.get('_research_title')
    if title is None:
        title=norm(record.get('law') or record.get('title') or '')
        record['_research_title']=title
    if token_freq is None:
        tokens=_research_tokens(text)
        if not tokens:
            return 0, []
        freq={}
        for t in tokens: freq[t]=freq.get(t,0)+1
    else:
        freq=token_freq
        if not freq:
            return 0, []
    matched=[]
    score=0.0
    unique=set(query_terms)|set(expanded_terms)
    for t in unique:
        if t in freq:
            # Smoothed IDF: rare legal terms matter more than generic ones.
            import math
            idf=math.log((total_docs+1)/(df.get(t,0)+1))+1
            tf=1+math.log(freq[t])
            weight=1.0 if t in expanded_terms and t not in query_terms else 1.35
            score += idf*tf*weight
            matched.append(t)
            if t in title: score += 2.5
    nq=query_norm if query_norm is not None else norm(clean_legal_text(query))
    for phrase in query_phrases:
        p=norm(phrase)
        if p and p in text:
            score += 9
            matched.append(phrase)
    if nq and len(nq)>=4 and nq in text:
        score += 7
    if nq and title and nq in title:
        score += 12
    number=query_number if query_number is not None else _research_number(query)
    if number:
        article=record.get('_research_article_ascii')
        if article is None:
            article=str(record.get('article') or '').translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹','0123456789'))
            record['_research_article_ascii']=article
        if article == number:
            score += 55
    intent=query_intent if query_intent is not None else _source_intent(query)
    kind=record.get('kind','law')
    if intent:
        if kind in intent: score += 12
        elif kind in {'sample','circular'} and ('law' in intent): score -= 2
        elif kind not in intent and ('ruling' in intent or 'consultation' in intent or 'sample' in intent or 'circular' in intent):
            score -= 8
    status=record.get('source_status','')
    # Verification is a ranking signal, never a substitute for relevance.
    if status in {'verified','verified_current'}: score += 2.0
    elif status in {'source_verified_text_pending','user_provided_text','user_provided_pdf'}: score += 0.25
    elif status in {'bundled_text_unverified','source_pending_import'}: score -= 0.5
    return score, sorted(set(matched), key=lambda x:(-len(str(x)),str(x)))[:10]


def _build_unified_legal_corpus():
    corpus=[]
    seen=set()
    for collection in (INDEX, RULING_INDEX, CONSULTATION_INDEX):
        for record in collection:
            item=dict(record)
            item.setdefault('kind','law')
            key=(item.get('kind'), item.get('law'), item.get('article'),
                 item.get('ruling_number'), item.get('consultation_number'), item.get('title'))
            if key in seen:
                continue
            seen.add(key)
            corpus.append(item)
    return corpus

# V140: one source of truth for ordinary search and case relevance.
LEGAL_CORPUS = _build_unified_legal_corpus()


def _research_corpus():
    return LEGAL_CORPUS


# V139: build search statistics once per process and persist them across
# restarts.  The cache contains only derived lexical statistics; the legal
# source records are always rebuilt from the bundled JSON files in this process.
_RESEARCH_STATS = None
_RESEARCH_STATS_CACHE_VERSION = 2
_RESEARCH_STATS_CACHE_FILE = LAW_FILE.parent / '.legal_research_stats_v140.pkl'

def _research_stats_fingerprint():
    # Any source that can change the searchable corpus or its tokenization
    # invalidates the derived cache. Missing files are represented explicitly.
    paths = [
        LAW_FILE,
        RULINGS_FILE,
        CONSULTATIONS_FILE,
        SAMPLES_FILE,
        LAW_FILE.parent / 'persian_spacing_lexicon.json',
    ]
    parts = [f'v{_RESEARCH_STATS_CACHE_VERSION}']
    for path in paths:
        try:
            st = path.stat()
            parts.append(f'{path.name}:{st.st_mtime_ns}:{st.st_size}')
        except OSError:
            parts.append(f'{path.name}:missing')
    return '|'.join(parts)

def _load_research_stats_cache(fingerprint, corpus_len):
    try:
        import pickle
        with open(_RESEARCH_STATS_CACHE_FILE, 'rb') as f:
            payload = pickle.load(f)
        if not isinstance(payload, dict):
            return None
        if payload.get('version') != _RESEARCH_STATS_CACHE_VERSION:
            return None
        if payload.get('fingerprint') != fingerprint:
            return None
        freqs = payload.get('freqs')
        df = payload.get('df')
        total = payload.get('total')
        if not isinstance(freqs, list) or not isinstance(df, dict):
            return None
        if len(freqs) != corpus_len or int(total or 0) != corpus_len:
            return None
        return (freqs, df, max(1, int(total)))
    except (OSError, EOFError, ValueError, TypeError, ImportError, pickle.UnpicklingError):
        return None

def _save_research_stats_cache(fingerprint, freqs, df, total):
    try:
        import pickle, tempfile
        cache_dir = _RESEARCH_STATS_CACHE_FILE.parent
        cache_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix='.legal_research_stats_v140_',
            suffix='.tmp',
            dir=str(cache_dir),
        )
        try:
            with os.fdopen(fd, 'wb') as f:
                pickle.dump({
                    'version': _RESEARCH_STATS_CACHE_VERSION,
                    'fingerprint': fingerprint,
                    'freqs': freqs,
                    'df': df,
                    'total': total,
                }, f, protocol=pickle.HIGHEST_PROTOCOL)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_name, _RESEARCH_STATS_CACHE_FILE)
        finally:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass
    except (OSError, ValueError, TypeError, ImportError):
        # Cache is an optimization only; search must remain fully functional
        # when the deployment filesystem is read-only.
        return

def _build_research_stats(corpus):
    freqs=[]
    df={}
    for rec in corpus:
        text=rec.get('ntext') or norm(rec.get('clean_text') or rec.get('text') or '')
        tokens=re.findall(r'[\wآ-ی]+', text)
        freq={}
        for t in tokens:
            if len(t)>=2 and t not in _RESEARCH_STOPWORDS:
                freq[t]=freq.get(t,0)+1
        freqs.append(freq)
        for t in freq:
            df[t]=df.get(t,0)+1
    return freqs, df, max(1,len(corpus))

def _research_stats():
    global _RESEARCH_STATS
    if _RESEARCH_STATS is not None:
        return _RESEARCH_STATS

    corpus=_research_corpus()
    fingerprint=_research_stats_fingerprint()
    cached=_load_research_stats_cache(fingerprint, len(corpus))
    if cached is not None:
        freqs, df, total = cached
    else:
        freqs, df, total = _build_research_stats(corpus)
        _save_research_stats_cache(fingerprint, freqs, df, total)

    _RESEARCH_STATS=(corpus, freqs, df, total)
    return _RESEARCH_STATS


def search_legal_research(q, limit=8):
    """V130 auditable hybrid retrieval for Iranian legal sources.

    Returns the same record shape as ``search`` plus ``matched_terms`` and a
    bounded ``retrieval_score``. No generated legal conclusion is introduced.
    """
    q=str(q or '').strip()
    if not q:
        return []
    limit=max(1,min(int(limit or 8),20))
    phrases,base_terms=_terms(q)
    expanded_terms=[]
    try:
        for item in expand_query(q):
            expanded_terms.extend(_terms(item)[1])
    except Exception:
        expanded_terms=[]
    base_terms=list(dict.fromkeys(_research_tokens(' '.join(base_terms))))
    expanded_terms=list(dict.fromkeys(_research_tokens(' '.join(expanded_terms))))
    all_terms=list(dict.fromkeys(base_terms+expanded_terms))[:40]

    # V139-P1: compute query-wide signals once, not once for every corpus record.
    query_norm=norm(clean_legal_text(q))
    query_number=_research_number(q)
    query_intent=_source_intent(q)

    corpus,freqs,df,total=_research_stats()
    scored=[]
    for rec,freq in zip(corpus,freqs):
        score,matched=_research_score(
            q,rec,df,total,base_terms,phrases,expanded_terms,freq,
            query_norm=query_norm, query_number=query_number, query_intent=query_intent
        )
        if score < 3:
            continue
        item=dict(rec)
        item['retrieval_score']=round(score,3)
        item['matched_terms']=matched
        # Human-readable retrieval metadata; it is deliberately not a legal conclusion.
        item['retrieval_note']='بر اساس تطبیق عبارت/واژه، توسعه اصطلاحات، شماره ماده و نوع منبع رتبه‌بندی شده است.'
        item['citation']=item.get('citation') or citation_for_record(item)
        scored.append(item)
    scored.sort(key=lambda x:(-x['retrieval_score'], x.get('kind','law'), x.get('law',''), str(x.get('article',''))))

    # Deterministic source diversity: don't let one statute consume the entire top list.
    out=[]; law_counts={}; kind_counts={}
    for item in scored:
        key=(item.get('kind','law'), item.get('law',''))
        max_same=4 if item.get('kind','law')=='law' else 3
        if law_counts.get(key,0)>=max_same:
            continue
        # Prefer at most 5 consecutive results of the same source kind unless
        # the query explicitly names that source type.
        if kind_counts.get(item.get('kind','law'),0)>=5 and item.get('kind') not in _source_intent(q):
            continue
        out.append(item)
        law_counts[key]=law_counts.get(key,0)+1
        kind_counts[item.get('kind','law')]=kind_counts.get(item.get('kind','law'),0)+1
        if len(out)>=limit:
            break
    return out


def search(q,limit=8):
    # Keep the public API stable while routing normal searches through the V130
    # retrieval layer. Existing formatters can consume the same record fields.
    return search_legal_research(q, limit)


# V142: auditable source lookup and deterministic cross-source relations.
# These helpers never invent a legal relationship; they only expose metadata
# already present in the corpus and lexical overlap between stored records.
_CITATION_RECORD_INDEX = None

def _citation_records():
    global _CITATION_RECORD_INDEX
    if _CITATION_RECORD_INDEX is None:
        idx = {}
        for rec in LEGAL_CORPUS:
            citation = rec.get('citation') or {}
            cid = citation.get('id')
            if cid:
                idx[str(cid)] = rec
        _CITATION_RECORD_INDEX = idx
    return _CITATION_RECORD_INDEX

def get_source_record(citation_id):
    """Return one corpus record by its stable citation id, or None."""
    return _citation_records().get(str(citation_id or '').strip())

def _relation_terms(record):
    text = ' '.join(str(record.get(k) or '') for k in ('law','title','article','ruling_number','consultation_number','question','clean_text','text'))
    return set(_research_tokens(text))

def related_sources(record, limit=6):
    """Find conservative, lexical cross-source links for a corpus record.

    This is deliberately not presented as a legal conclusion. A relation is
    only a navigational research hint based on shared substantive terms,
    exact law/title identity, or explicit source metadata.
    """
    if not isinstance(record, dict):
        return []
    own_id = (record.get('citation') or {}).get('id')
    own_terms = _relation_terms(record)
    if not own_terms:
        return []
    own_kind = record.get('kind','law')
    own_law = str(record.get('law') or '').strip()
    scored=[]
    for other in LEGAL_CORPUS:
        ocid=(other.get('citation') or {}).get('id')
        if not ocid or ocid == own_id:
            continue
        other_terms=_relation_terms(other)
        overlap=own_terms & other_terms
        if not overlap:
            continue
        score=0.0
        # Title/source identity is a strong navigational signal.
        if own_law and own_law == str(other.get('law') or '').strip():
            score += 7
        if own_kind != other.get('kind'):
            score += 2.5  # encourage cross-source discovery
        score += min(len(overlap), 8) * 1.7
        # Longer substantive terms are more useful than generic overlaps.
        score += sum(min(len(t), 12) / 20 for t in overlap if len(t) >= 5)
        if score >= 5:
            scored.append((score, other, overlap))
    scored.sort(key=lambda x:(-x[0], x[1].get('kind','law'), str(x[1].get('law') or x[1].get('title') or ''), str(x[1].get('article') or '')))
    out=[]; kind_counts={}
    for score, other, overlap in scored:
        kind=other.get('kind','law')
        if kind_counts.get(kind,0)>=2 and len(out)<limit:
            continue
        item=dict(other)
        item['relation_score']=round(score,2)
        item['relation_terms']=sorted(overlap, key=lambda x:(-len(x),x))[:6]
        out.append(item)
        kind_counts[kind]=kind_counts.get(kind,0)+1
        if len(out)>=max(1,min(int(limit or 6),10)):
            break
    return out
