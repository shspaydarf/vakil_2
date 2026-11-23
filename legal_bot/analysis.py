from persian_case_search import search_pages, search_text_with_pages
import re
from .files import clean_fa
from .glossary import expand_query
from .important_terms import matching_phrases, category_counts
from .source_quality import source_segment_ok, is_probable_source_noise

RULES=[
('🔴','وجه التزام/جریمه',['وجه التزام','وجه‌التزام','جریمه تاخیر','جریمه تأخیر','خسارت مقطوع','خسارت قراردادی']),
('🟠','فسخ/خاتمه',['فسخ','خاتمه قرارداد','اقاله','انحلال قرارداد']),
('🟠','حل اختلاف/داوری',['داوری','حل اختلاف','مرجع حل اختلاف','داور']),
('🟡','قوه قهریه',['قوه قهریه','فورس ماژور','فورس‌ماژور','حادثه خارج از اختیار']),
('🟠','تضمین/ضمانت',['ضمانت','تضمین','چک ضمانت','ضامن','وثیقه']),
('🟡','محرمانگی/عدم افشا',['محرمانگی','اطلاعات محرمانه','عدم افشا']),
('🟠','تمدید/تجدید خودکار',['تمدید خودکار','به طور خودکار تمدید','تجدید خودکار']),
('🔴','اسقاط/سلب حقوق',['اسقاط کافه خیارات','سلب حق','اسقاط حقوق','اسقاط خیارات']),
('🟠','واگذاری/انتقال تعهد',['واگذاری قرارداد','انتقال قرارداد','انتقال تعهد','واگذاری تعهد']),
('🟡','صلاحیت/مرجع قضایی',['صلاحیت دادگاه','مرجع قضایی','دادگاه صالح']),
('🟡','مهلت/سررسید',['سررسید','مهلت','موعد','تا تاریخ','ظرف مدت']),
('🟡','پرداخت/اقساط',['پرداخت','قسط','اقساط','ثمن','اجرت']),
]
MONTHS='فروردین|اردیبهشت|خرداد|تیر|مرداد|شهریور|مهر|آبان|آذر|دی|بهمن|اسفند'

def _pages(text):
    text=clean_fa(text)
    matches=list(re.finditer(r'\[صفحه\s+(\d+)\]',text))
    if not matches:return [(None,text)]
    out=[]
    for i,m in enumerate(matches):
        end=matches[i+1].start() if i+1<len(matches) else len(text)
        body=text[m.end():end].strip()
        if body:out.append((int(m.group(1)),body))
    return out

def _source_pages(text,term,expand=True):
    """Find source pages for a signal.

    Search/retrieval may use glossary aliases, but risk badges shown to the
    lawyer must not silently fire on a synonym that never appears in the
    source.  ``expand=False`` is therefore used for the risk engine.
    """
    variants=expand_query(term) if expand else [term]
    variants=variants or [term]
    pages=[]
    for p,t in _pages(text):
        norm_t=t.replace('‌',' ')
        for v in variants:
            vv=str(v or '').replace('‌',' ')
            if not vv: continue
            # Flexible whitespace, exact phrase; no substring expansion.
            pat=re.escape(vv).replace(r'\ ',r'\s*')
            if re.search(pat,norm_t,re.I):
                pages.append(p); break
    return list(dict.fromkeys(pages))[:8]
def _find_all(pattern,text,flags=re.I): return [m.group(1).strip() for m in re.finditer(pattern,text,flags)]
def _page_for_value(pages,value): return next((p for p,b in pages if value in b),None)

def _sentences(body):
    # PDF/OCR output often loses Persian punctuation. Newlines are therefore
    # meaningful boundaries, but very short fragments are ignored.
    chunks=re.split(r'(?<=[.!؟؛])\s+|[\r\n]+',body)
    out=[]
    for x in chunks:
        x=re.sub(r'\s+',' ',x).strip(' -•▪◦')
        if len(x)>=25 and source_segment_ok(x, min_chars=25): out.append(x)
    return out

def _all_candidate_sentences(text,limit=80):
    """Return substantive source sentences even when legal keywords are absent."""
    out=[]; seen=set()
    for page,body in _pages(text):
        for sent in _sentences(body):
            key=re.sub(r'\s+',' ',sent).strip()
            if key in seen or not source_segment_ok(key, min_chars=25): continue
            seen.add(key); out.append((page,key[:650]))
            if len(out)>=limit: return out
    return out

def _snippets(text,limit=40):
    keys=r'قرارداد|تعهد|مبلغ|پرداخت|فسخ|خسارت|خواهان|خوانده|طرفین|ادعا|تاریخ|مطالبه|رأی|دادخواست|شرط|داوری|سررسید|مرجع|ابلاغ|صلاحیت|اظهارنامه|تأمین|اقرار|شهادت|ضمان|رهن|انفساخ|بطلان|عدم نفوذ|مهریه|نفقه|طلاق|حضانت|اجاره|تخلیه|چک|سفته|وجه التزام|الزام|محکومیت|تحویل|استرداد|ابطال|تنفیذ|تصرف|خسارتی|کارشناس|شاکی|مشتکی|وکیل|شعبه|پرونده|کلاسه|دادگاه|اجرائیه|توقیف|تأمین دلیل|معاینه|اسناد|رسید|شماره حساب|شبا|سود|تأخیر|اعسار|تقسیط|صلح|سازش|شورای حل اختلاف|داور|بیع|مبیع|ثمن|رهن|مستأجر|موجر|ودیعه|سفته|ظهرنویس'
    legal=[]
    for page,body in _pages(text):
        for s in _sentences(body):
            if re.search(keys,s): legal.append((page,s[:650]))
    # Critical fallback: never turn a usable document into an empty summary just
    # because OCR/native extraction did not preserve the expected legal keywords.
    candidates=legal if legal else _all_candidate_sentences(text,limit=max(30,limit*4))
    seen=set(); result=[]
    for x in candidates:
        key=(x[0],x[1])
        if key in seen: continue
        pages_seen={p for p,_ in result}
        if x[0] not in pages_seen or len(result)<min(6,limit):
            result.append(x); seen.add(key)
        if len(result)>=limit: break
    if len(result)<limit:
        for x in candidates:
            key=(x[0],x[1])
            if key in seen: continue
            result.append(x); seen.add(key)
            if len(result)>=limit: break
    return result

def _extract_parties(text,pages):
    """Extract party identities conservatively.

    A role word by itself (e.g. «خوانده متعهد است ...») is not a party
    identity.  Prefer explicit labelled fields and «به طرفیت/علیه» phrases.
    """
    out=[]; seen=set()
    role_pat=r'(?:خواهان|شاکی|موکل|شکات|خوانده|مشتکی\s*عنه|طرف\s*مقابل|متهم|کارفرما|پیمانکار|فروشنده|خریدار|موجر|مستأجر|متعهدله|طرف\s*اول|طرف\s*دوم|مالک|متصرف|زوج|زوجه|ضامن|متعهد)'
    # Explicit label: «خواهان: علی رضایی» / «طرف اول - شرکت الف».
    labelled=re.compile(rf'(?m)^\s*({role_pat})\s*[:：\-]\s*([^\n،؛.]+)')
    for m in labelled.finditer(text):
        role=m.group(1).strip(); name=m.group(2).strip()
        # Cut sentence tails after common narrative/verb boundaries.
        name=re.split(r'\s+(?=(?:از|که|وضعیت|درخواست|تقاضا|مطالبه|اعلام|ادعا|دارد|دارند|است|هست|هستند|می[‌ ]?باشد|می[‌ ]?کند|کرده|شد|شده)\b)', name, maxsplit=1)[0]
        name=re.sub(r'\s+',' ',name).strip(' .،؛:-')
        if len(name)<2 or len(name)>80 or len(name.split())>8: continue
        if len(name) >= 20 and is_probable_source_noise(name): continue
        key=(role,name)
        if key not in seen:
            seen.add(key); p=_page_for_value(pages,name); out.append({'name':name,'role':role,'source_pages':[p] if p is not None else []})

    # Explicit procedural phrases: «به طرفیت ...» / «علیه ...».
    proc=re.compile(r'(?:به\s+طرفیت|علیه|له)\s+([^\n،؛.]{2,100})',re.I)
    for m in proc.finditer(text):
        name=m.group(1).strip()
        name=re.split(r'\s+(?=(?:در|که|وضعیت|درخواست|تقاضا|مطالبه|اعلام|ادعا|است|هست|هستند|می[‌ ]?باشد|می[‌ ]?کند|کرده|شد|شده)\b)', name, maxsplit=1)[0]
        name=re.sub(r'\s+',' ',name).strip(' .،؛:-')
        if len(name)<2 or len(name)>80 or len(name.split())>8: continue
        if len(name) >= 20 and is_probable_source_noise(name): continue
        key=('طرف/مخاطب',name)
        if key not in seen:
            seen.add(key); p=_page_for_value(pages,name); out.append({'name':name,'role':'طرف/مخاطب','source_pages':[p] if p is not None else []})
    return out[:20]

def _extract_dates(text,pages):
    vals=[]
    for pat in [r'\b([0-9۰-۹]{4}[/-][0-9۰-۹]{1,2}[/-][0-9۰-۹]{1,2})\b',rf'\b([0-9۰-۹]{{1,2}}\s*(?:{MONTHS})\s*[0-9۰-۹]{{4}})\b']:
        vals += re.findall(pat,text)
    out=[]; seen=set()
    for v in vals:
        if v in seen: continue
        seen.add(v); p=_page_for_value(pages,v); out.append({'value':v,'event':'ذکرشده در سند','source_pages':[p] if p else []})
    return out[:30]

def _extract_amounts(text,pages):
    # Start only at a number boundary.  The previous pattern could restart
    # inside «۵۰۰٬۰۰۰٬۰۰۰» and return the tail «۰۰۰ تومان».
    pat=(r'(?<![0-9۰-۹,،٬.])'
         r'((?:[0-9۰-۹]{1,3}(?:[ ,،٬.][0-9۰-۹]{3})+|[0-9۰-۹]{4,})'
         r'(?:\s+(?:هزار|میلیون|میلیارد))?\s*(?:تومان|ریال))')
    out=[]; seen=set()
    for m in re.finditer(pat,text):
        v=re.sub(r'\s+',' ',m.group(1)).strip()
        # Do not let a date fragment masquerade as money.
        if re.search(r'[0-9۰-۹]{4}[/-][0-9۰-۹]{1,2}[/-][0-9۰-۹]{1,2}',v):
            continue
        if v in seen: continue
        seen.add(v); p=_page_for_value(pages,v); out.append({'value':v,'context':text[max(0,m.start()-45):m.start()].strip()[-45:],'source_pages':[p] if p else []})
    return out[:30]

def _legal_refs(text,pages):
    out=[]; seen=set()
    for m in re.finditer(r'(?:ماده|مواد)\s+([0-9۰-۹]+(?:\s*(?:و|تا)\s*[0-9۰-۹]+)?)\s*(?:قانون\s+([^\n،؛.]{2,80}))?',text,re.I):
        ref='ماده '+m.group(1).strip()+((' قانون '+m.group(2).strip()) if m.group(2) else '')
        p=_page_for_value(pages,m.group(0)); key=(ref,p)
        if key not in seen: seen.add(key); out.append({'reference':ref,'source_pages':[p] if p else []})
    return out[:40]

def _timeline(dates,claims):
    # Deterministic timeline: preserve source order; no invented chronology.
    return [{'date':d['value'],'event':d['event'],'source_pages':d.get('source_pages',[])} for d in dates[:20]]

def _claim_candidate(sent: str) -> bool:
    """Require a sentence to look like an actual party position/request.

    A legal keyword alone is not enough: generic contract clauses, headings,
    document metadata and OCR fragments must not become claims.
    """
    t=re.sub(r"\s+", " ", sent or "").strip()
    if len(t) < 30 or not source_segment_ok(t, min_chars=30): return False
    # Explicit claim/position/request markers.
    explicit=(r"خواهان|خوانده|شاکی|مشتکی|مدعی|مدعی علیه|موکل|طرفین|ادعا(?:ی)?|"
              r"درخواست(?: می| دارد| شده| شد)|مطالبه(?: می| دارد| شده| شد)|"
              r"تقاضا(?: می| دارد| شده| شد)|دفاع(?: می| دارد| کرد| شده)|"
              r"اعتراض(?: می| دارد| کرد| شده)|محکومیت(?: می| خواست)|"
              r"الزام(?: به| می)|ابطال(?: را| می)|فسخ(?: را| می)|"
              r"اعسار|تقسیط|مهریه|نفقه|حضانت|اجرت\s*المثل|تخلیه|استرداد|تنفیذ")
    if not re.search(explicit,t,re.I): return False
    # Reject metadata/header-like fragments.
    if re.fullmatch(r"[\s:؛،.-]*(?:پرونده|کلاسه|دادنامه|تجدیدنظرخواهی|شماره)\s*[0-9۰-۹/\-]+[\s.؛،-]*", t): return False
    alpha=len(re.findall(r"[آ-یA-Za-z]",t)); digits=len(re.findall(r"[0-9۰-۹]",t))
    if alpha < 12 or digits > max(18, alpha*2): return False
    # A sentence consisting mostly of a contract/legal noun list is not a claim.
    nouns=len(re.findall(r"(?:قرارداد|تعهد|ماده|شرط|پرداخت|مبلغ|مهلت|سررسید|دادگاه|قانون|سند)",t))
    verbs=len(re.findall(r"(?:است|هست|باشد|شد|کرد|می\s*کند|می\s*شود|خواهد|درخواست|مطالبه|ادعا|اعتراض|تقاضا)",t))
    return verbs >= 1 and nouns <= 8

def _extract_claims(text,pages):
    """Extract explicit litigation demands/positions without inventing facts."""
    out=[]; seen=set()
    for p,b in pages:
        for sent in _sentences(b):
            if not _claim_candidate(sent):
                continue
            key=re.sub(r"\s+"," ",sent).strip()
            if key in seen: continue
            seen.add(key)
            actor='نامشخص'
            if re.search(r"خواهان|مدعی|شاکی|موکل",key): actor='سمتِ مدعی/خواهان'
            elif re.search(r"خوانده|مدعی علیه|مشتکی|طرف مقابل",key): actor='سمتِ خوانده/طرف مقابل'
            elif re.search(r"طرفین",key): actor='طرفین'
            kind='درخواست/ادعا'
            if re.search(r"دفاع|انکار|اعتراض",key): kind='دفاع/اعتراض'
            elif re.search(r"مطالبه|درخواست|تقاضا|محکومیت|الزام",key): kind='درخواست/مطالبه'
            out.append({'claim':key[:700],'source_pages':[p] if p is not None else [],'actor':actor,'claim_type':kind,'source_text':key[:700]})
            if len(out)>=35: return out
    return out


def _extract_sensitive_clauses(text,pages):
    """Find legally sensitive clauses/phrases and preserve source wording."""
    groups={
      'حق فسخ':r'حق\s+فسخ|خیار\s+فسخ|فسخ\s+قرارداد',
      'انفساخ':r'انفساخ|منفسخ',
      'اسقاط خیارات':r'اسقاط\s+خیارات|اسقاط\s+کافه\s+خیارات|خیارات.*اسقاط',
      'وجه التزام':r'وجه\s+التزام|خسارت\s+تأخیر',
      'شرط داوری':r'شرط\s+داوری|داور|داوری',
      'ضمان/وثیقه':r'ضمانت|ضامن|وثیقه|رهن|تضمین',
      'اقرار/اسقاط حق':r'اقرار|اسقاط\s+حق|صرف\s*نظر|رضایت\s+قطعی',
      'مهلت/سررسید':r'سررسید|مهلت|موعد|ظرف\s+مدت',
      'عدم انتقال/محدودیت':r'عدم\s+انتقال|ممنوع\s+از\s+انتقال|عدم\s+واگذاری|عدم\s+رقابت',
      'شرط تعلیقی':r'شرط\s+تعلیقی|معلق|منوط\s+به',
      'محرمانگی':r'محرمانگی|محرمانه|عدم\s+افشا',
      'چک/سفته':r'چک|سفته',
      'اجاره/تخلیه':r'اجاره|تخلیه|ودیعه|رهن\s*مسکن|سقف\s*اجاره',
      'خانواده':r'مهریه|نفقه|طلاق|حضانت|ملاقات|اجرت\s*المثل',
      'اعسار/تقسیط':r'اعسار|تقسیط|ناتوانی\s*از\s*پرداخت',
      'اجرا/توقیف':r'اجرائیه|اجرای\s*احکام|توقیف|تأمین\s*خواسته',
      'کارشناسی/دلیل':r'کارشناس|تأمین\s*دلیل|معاینه\s*محل|شهادت\s*شهود|استماع',
      'مرجع رسیدگی':r'دادگاه|شعبه|شورای\s*حل\s*اختلاف|داوری|دیوان',

    }
    out=[]; seen=set()
    for p,b in pages:
        for sent in _sentences(b):
            for label,pat in groups.items():
                if re.search(pat,sent,re.I):
                    key=(label,sent)
                    if key in seen: continue
                    seen.add(key); out.append({'label':label,'text':sent[:700],'source_pages':[p] if p else []})
            if len(out)>=40: return out
    return out

def _extract_important_terms(text, limit=80):
    """Detect important words/phrases across legal and non-legal case language.

    These are signals, not legal conclusions or synonym substitutions.  The
    lexicon deliberately includes ordinary words, evidence/media, identifiers,
    money, dates and sensitive phrases because they often carry more case
    value than rare legal terminology.
    """
    hits=[]
    for use in ('party','procedural','contract','property','financial','criminal','family','employment','accident','evidence','narrative','warning','identifier','money'):
        for phrase in matching_phrases(text, use=use, limit=limit):
            if phrase not in [x['phrase'] for x in hits]:
                hits.append({'phrase':phrase,'use':use})
            if len(hits)>=limit:
                return hits
    return hits

def _contradictions(amounts,dates):
    out=[]
    uniq=list(dict.fromkeys(x['value'] for x in amounts))
    if len(uniq)>1: out.append({'type':'amounts','message':'چند مبلغ متفاوت در متن شناسایی شد؛ تطبیق با اصل سند لازم است.','values':uniq[:8],'source_pages':sorted({p for x in amounts for p in x.get('source_pages',[])})})
    du=list(dict.fromkeys(x['value'] for x in dates))
    if len(du)>1: out.append({'type':'dates','message':'چند تاریخ متفاوت شناسایی شد؛ نقش هر تاریخ باید با متن اطراف آن بررسی شود.','values':du[:12],'source_pages':sorted({p for x in dates for p in x.get('source_pages',[])})})
    return out

def _rank_summary_sentences(text, snippets, limit=20):
    """Select source sentences for a safe, extractive baseline summary."""
    if not snippets: return []
    keys=('خواهان','خوانده','شاکی','مشتکی','خواسته','ادعا','مطالبه','قرارداد',
          'تعهد','متعهد','ملزم','باید','مبلغ','تومان','ریال','تاریخ','درخواست',
          'فسخ','خسارت','داوری','رأی','دادخواست','اظهارنامه','اقرار','دفاع',
          'ماده','قانون','پرداخت','ضمانت','وثیقه','تأمین','سررسید')
    scored=[]
    for i,x in enumerate(snippets):
        t=x.get('text','')
        score=sum(2 for k in keys if k in t)
        if re.search(r'[0-9۰-۹]{2,}',t): score+=2
        score += max(0,4-i*0.08)
        scored.append((score,i,x))
    scored.sort(key=lambda z:(-z[0],z[1]))
    chosen=[]; pages=set()
    for _,_,x in scored:
        pg=x.get('page')
        if pg not in pages or len(chosen)>=limit-2:
            chosen.append(x); pages.add(pg)
        if len(chosen)>=limit: break
    return chosen



def _extract_courts_and_refs(text, pages):
    """Court / branch / case-number style signals (extractive)."""
    out=[]; seen=set()
    pats = [
        r'(دادگاه\s+[^\n،؛]{3,60})',
        r'(شعبه\s*[0-9۰-۹]+\s*[^\n،؛]{0,40})',
        r'(کلاسه\s*[:：]?\s*[^\n،؛\s]{3,40})',
        r'(پرونده\s*[:：]?\s*[^\n،؛]{3,40})',
        r'(شورای\s+حل\s+اختلاف\s*[^\n،؛]{0,40})',
        r'(اجرای\s+احکام\s*[^\n،؛]{0,40})',
        r'(دیوان\s+(?:عالی|عدالت)\s*[^\n،؛]{0,40})',
    ]
    for pat in pats:
        for m in re.finditer(pat, text, re.I):
            v = re.sub(r'\s+', ' ', m.group(1)).strip(' .،؛')
            if len(v)<5 or v in seen: continue
            seen.add(v)
            p=_page_for_value(pages, v[:30])
            out.append({'value':v, 'source_pages':[p] if p else []})
            if len(out)>=20: return out
    return out


def _extract_evidence_signals(text, pages):
    """Mentions of evidence / proof sources without concluding weight."""
    terms=r'شهادت|گواه|استماع|کارشناس|تأمین\s*دلیل|معاینه\s*محل|سند\s*رسمی|سند\s*عادی|رسید|پیامک|پیامک‌ها|فیلم|تصویر|پرینت|حساب|شبا|فیش|قرارداد|اقرار|اظهارنامه|ابلاغ|روزنامه|سامانه\s*ثنا'
    out=[]; seen=set()
    for p,b in pages:
        for sent in _sentences(b):
            if re.search(terms, sent):
                key=sent.strip()
                if key in seen or len(key)<20: continue
                seen.add(key)
                out.append({'text':key[:700], 'source_pages':[p] if p else []})
            if len(out)>=20: return out
    return out


def _extract_remedies(text, pages):
    """Requested or ordered remedies phrased in the document."""
    terms=r'محکومیت|الزام\s*به|استرداد|پرداخت\s*مبلغ|تخلیه|تحویل|ابطال|تنفیذ|توقف|توقیف|اعسار|تقسیط|صدور\s*اجرائیه|جبران\s*خسارت|وجه\s*التزام|نفقه|مهریه|اجرت'
    out=[]; seen=set()
    for p,b in pages:
        for sent in _sentences(b):
            if re.search(terms, sent):
                key=sent.strip()
                if key in seen or len(key)<20: continue
                seen.add(key)
                out.append({'text':key[:700], 'source_pages':[p] if p else []})
            if len(out)>=25: return out
    return out


def _guess_document_type(text):
    t=text[:4000]
    rules=[
        ('دادخواست', r'دادخواست|ریاست محترم|احتراماً به استحضار'),
        ('لایحه', r'لایحه|در پاسخ به|به استحضار می‌رساند'),
        ('رأی/دادنامه', r'دادنامه|رأی\s*صادر|حکم\s*به'),
        ('قرارداد', r'طرفین قرارداد|قرارداد\s+(?:فروش|اجاره|خدمات|پیمان|مشارکت|ساختمان|صلح|وکالت|استخدام)|ماده\s*۱|مبیع|ثمن|موجر|مستأجر'),
        ('اظهارنامه', r'اظهارنامه|مخاطب'),
        ('چک/سفته', r'چک\s*شماره|سفته|ظهرنویس'),
        ('اجرائیه', r'اجرائیه|اجرای احکام'),
    ]
    for label, pat in rules:
        if re.search(pat, t):
            return label
    return ''


def _case_intelligence(text, pages, parties, claims, evidence, refs, dates, amounts, sensitive, contradictions, document_type):
    """Build a conservative, source-backed case intelligence layer.

    This is intentionally local/extractive: it identifies signals and gaps but
    never declares a legal conclusion or invents a missing fact.
    """
    # This legacy intelligence view is a compact signal summary, not the
    # authoritative issue map (V152). Keep only domain-specific axes here so
    # generic words such as «پرداخت»، «سند»، «دادگاه» or «ابلاغ» do not create
    # a second, noisy checklist beside V152.
    issue_rules = [
        ('خانواده', r'مهریه|نفقه|طلاق|حضانت|ملاقات|تمکین|اجرت\s*المثل|زوج|زوجه'),
        ('قرارداد و تعهدات', r'قرارداد|عقد|تعهد|متعهد|متعهدله|نقض\s+تعهد'),
        ('فسخ/بطلان/انحلال', r'فسخ|اقاله|انفساخ|بطلان|عدم\s+نفوذ|ابطال'),
        ('اجرای حکم', r'اجرائیه|اجراییه|اجرای\s+احکام|محکومیت|مزایده'),
        ('چک و اسناد تجاری', r'چک|سفته|ظهرنویس|گواهی\s+عدم\s+پرداخت'),
        ('اجاره و تخلیه', r'موجر|مستأجر|اجاره|تخلیه|ودیعه'),
        ('داوری/حل اختلاف', r'داوری|داور|حل\s+اختلاف|مرجع\s+حل\s+اختلاف'),
        ('اموال/مالکیت', r'مالکیت|مالک|خلع\s+ید|تصرف\s+عدوانی|مبیع|رهن|وثیقه'),
    ]
    issues=[]
    for label,pat in issue_rules:
        hits=[]
        for pg,body in pages:
            for sent in _sentences(body):
                if re.search(pat,sent,re.I) and source_segment_ok(sent, min_chars=25):
                    hits.append({'text':sent[:500],'source_pages':[pg] if pg else []})
                    if len(hits)>=3: break
            if len(hits)>=3: break
        if hits:
            issues.append({'issue':label,'signals':hits})

    # Document/evidence gaps are framed as "not found in extracted text", not
    # as proof that the document does not exist.
    gap_checks = [
        ('مشخصات طرفین', bool(parties), 'نام/نقش طرفین در متن استخراج‌شده روشن نیست'),
        ('تاریخ‌های کلیدی', bool(dates), 'تاریخ یا مهلت کلیدی در متن استخراج‌شده پیدا نشد'),
        ('مبلغ/موضوع مالی', bool(amounts), 'مبلغ یا نشانه مالی روشن در متن استخراج‌شده پیدا نشد'),
        ('مبنای قانونی', bool(refs), 'ارجاع صریح به ماده/قانون در متن استخراج‌شده پیدا نشد'),
        ('ادله', bool(evidence), 'اشاره روشن به ادله یا مستندات در متن استخراج‌شده پیدا نشد'),
        ('خواسته/ادعا', bool(claims), 'خواسته یا ادعای صریح در متن استخراج‌شده پیدا نشد'),
    ]
    missing=[]
    for label,ok,msg in gap_checks:
        if not ok: missing.append({'item':label,'message':msg,'status':'not_found_in_extracted_text'})

    # Evidence matrix: connect explicit claims to nearby evidence signals.
    matrix=[]
    for claim in claims[:12]:
        ct=claim.get('claim','')
        claim_terms=[x for x in re.findall(r'[آ-یA-Za-z]{3,}',clean_fa(ct)) if len(x)>=4][:18]
        matches=[]
        for ev in evidence[:20]:
            et=ev.get('text','')
            overlap=sum(1 for term in claim_terms if term in clean_fa(et))
            if overlap:
                matches.append({'text':et[:450],'source_pages':ev.get('source_pages',[]),'overlap':overlap})
        matches.sort(key=lambda x:-x['overlap'])
        matrix.append({'claim':ct[:650],'claim_source_pages':claim.get('source_pages',[]),
                       'evidence':matches[:3], 'status':'supported_signal' if matches else 'no_matching_evidence_signal_found'})

    key_facts=[]
    for x in (parties[:6] + dates[:8] + amounts[:8] + refs[:8]):
        if isinstance(x,dict):
            if 'name' in x: textv=f"{x.get('role','طرف')}: {x.get('name','')}"
            elif 'value' in x: textv=str(x.get('value',''))
            elif 'reference' in x: textv=str(x.get('reference',''))
            else: continue
            if textv.strip(): key_facts.append({'fact':textv[:500],'source_pages':x.get('source_pages',[])})

    risk_flags=[]
    if contradictions: risk_flags.append({'type':'contradiction_review','message':'چند مقدار/تاریخ متفاوت در متن شناسایی شده و تطبیق با اصل سند لازم است.'})
    if sensitive: risk_flags.append({'type':'sensitive_clauses','message':f'{len(sensitive)} عبارت/بند حساس برای بازبینی استخراج شد.'})
    if not dates: risk_flags.append({'type':'date_gap','message':'تاریخ کلیدی در متن استخراج‌شده پیدا نشد؛ در صورت وجود، اصل سند و ابلاغ را بررسی کنید.'})
    if not refs: risk_flags.append({'type':'legal_basis_gap','message':'مبنای قانونی صریح در متن استخراج‌شده پیدا نشد؛ این به معنی نبود مبنای قانونی نیست.'})

    return {
        'document_type': document_type,
        'issues': issues[:12],
        'key_facts': key_facts[:25],
        'missing_items': missing[:10],
        'evidence_matrix': matrix[:12],
        'intelligence_flags': risk_flags[:10],
        'confidence_note':'این بخش بر پایه متن استخراج‌شده است؛ «پیدا نشدن» به معنی نبودن سند/واقعیت در پرونده نیست و نتیجه حقوقی قطعی ارائه نمی‌کند.'
    }

def analyze(text):
    # v54: lexical OCR corrections are deferred to the final user-visible output boundary.
    text=clean_fa(text); pages=_pages(text)
    risks=[]
    for icon,title,terms in RULES:
        hits=[]
        for term in terms:
            ps=_source_pages(text,term,expand=False)
            if ps: hits.append({'term':term,'pages':ps})
        if hits: risks.append({'icon':icon,'title':title,'hits':hits})
    parties=_extract_parties(text,pages); dates=_extract_dates(text,pages); amounts=_extract_amounts(text,pages); refs=_legal_refs(text,pages); claims=_extract_claims(text,pages); sensitive=_extract_sensitive_clauses(text,pages); important_terms=_extract_important_terms(text,limit=100)
    courts=_extract_courts_and_refs(text,pages); evidence=_extract_evidence_signals(text,pages); remedies=_extract_remedies(text,pages)
    document_type=_guess_document_type(text)
    # Safe baseline summary: source sentences are copied, not paraphrased.
    # This prevents silent changes to numbers, dates and names.
    snippets=[{'page':p,'text':s} for p,s in _snippets(text,limit=60)]
    key=[]
    for x in _rank_summary_sentences(text, snippets, limit=20):
        key.append({'fact':x['text'],'source_pages':[x['page']] if x['page'] else []})
    obligations=[]
    for p,b in pages:
        for s in _sentences(b):
            if re.search(r'(?:متعهد|موظف|مکلف|ملزم|تعهد|باید|موظف است|مکلف است|متعهد است|مکلف می‌باشد|ملزم است|عهده‌دار|مسئول پرداخت|مکلف به)',s):
                obligations.append({'text':s[:700],'source_pages':[p] if p else []})
                if len(obligations)>=25: break
        if len(obligations)>=25: break
    entities={}
    if amounts: entities['amount']={'value':amounts[0]['value'],'pages':amounts[0].get('source_pages',[]),'all_values':[x['value'] for x in amounts[:10]]}
    if dates: entities['date']={'value':dates[0]['value'],'pages':dates[0].get('source_pages',[]),'all_values':[x['value'] for x in dates[:10]]}
    overview = []
    if parties:
        overview.append('طرفین شناسایی‌شده: ' + '، '.join(
            f"{(p.get('role') or '').strip()} {(p.get('name') or '').strip()}".strip()
            for p in parties[:6]
        ))
    if amounts:
        overview.append('مبالغ کلیدی: ' + '؛ '.join(a.get('value','') for a in amounts[:5] if a.get('value')))
    if dates:
        overview.append('تاریخ‌های مهم: ' + '؛ '.join(d.get('value','') for d in dates[:6] if d.get('value')))
    if document_type:
        overview.append('نوع سند احتمالی: ' + document_type)
    if claims:
        overview.append('ادعا/خواسته نمونه: ' + (claims[0].get('claim') or claims[0].get('text') or '')[:180])
        if len(claims) > 1:
            overview.append(f'تعداد بندهای خواسته/ادعا: {len(claims)}')
    if remedies:
        overview.append('خواسته/اثر نمونه: ' + (remedies[0].get('text') or '')[:180])
    if courts:
        overview.append('مرجع/شناسه: ' + '؛ '.join(c.get('value','') for c in courts[:4]))
    if evidence:
        overview.append(f'اشارات دلیلی در متن: {len(evidence)} مورد')
    if refs:
        overview.append('مواد اشاره‌شده: ' + '، '.join(r.get('reference','') for r in refs[:5] if r.get('reference')))
    if not overview and snippets:
        overview = [s[1][:200] if isinstance(s, (list, tuple)) and len(s)>1 else str(s)[:200] for s in snippets[:5]]

    return {
      'version':'5.2','engine_version':'6.1-local-deep','summary':snippets,'overview':overview,
      'entities':entities,'parties':parties,'dates':dates,'amounts':amounts,'claims':claims,'sensitive_clauses':sensitive,
      'obligations':obligations[:25],'legal_references':refs[:40],'important_terms':important_terms,'important_term_categories':category_counts(),'timeline':_timeline(dates,[]),
      'contradictions':_contradictions(amounts,dates),'risks':risks,'courts':courts,'evidence':evidence,'remedies':remedies,'document_type':document_type,'document_pages':[p for p,_ in pages if p is not None],
      'case_intelligence': _case_intelligence(text,pages,parties,claims,evidence,refs,dates,amounts,sensitive,_contradictions(amounts,dates),document_type),
      'ai_used':False,'ai_policy':'local_only',
      'stats': {
          'parties': len(parties), 'dates': len(dates), 'amounts': len(amounts),
          'claims': len(claims), 'obligations': len(obligations), 'refs': len(refs),
          'snippets': len(snippets), 'courts': len(courts), 'evidence': len(evidence),
          'remedies': len(remedies), 'sensitive': len(sensitive),
      },
    }

def local_case_search(text,query,limit=8):
    q=clean_fa(query).strip()
    if not q:return []
    expanded=expand_query(q)
    terms=[]
    for item in expanded:
        terms.extend(x for x in re.split(r'\s+', item) if len(x)>=2)
    terms=list(dict.fromkeys(terms))
    out=[]
    for page,body in _pages(text):
        for sent in _sentences(body):
            score=sum(1 for t in terms if t in sent)
            if score: out.append((score,page,sent[:800]))
    out.sort(key=lambda x:(-x[0], x[1] or 999999))
    return [{'page':p,'text':s,'score':sc} for sc,p,s in out[:limit]]


# V5 Persian-aware search adapter.
# This adapter is intentionally additive: existing handlers keep working.
def local_case_search_v5(pages_or_text, query, max_results=20):
    """Search full extracted text with Persian normalization and page context.

    Accepts either:
      - [(page_number, page_text), ...]
      - a single full text string with optional PAGE markers.
    """
    if isinstance(pages_or_text, str):
        return search_text_with_pages(pages_or_text, query, max_results=max_results)
    return search_pages(pages_or_text, query, max_results=max_results)


def _full_extracted_pages_from_case(case):
    """Return [(page_no, full_extracted_page_text), ...] from a stored case.

    Priority is always full extracted/source text. Summary/result fields are
    deliberately ignored for search.
    """
    if not case:
        return []

    candidates = [
        case.get("pages"),
        case.get("extracted_pages"),
        case.get("page_texts"),
        case.get("document_pages"),
    ]

    for pages in candidates:
        if isinstance(pages, dict):
            out = []
            for k, v in pages.items():
                try:
                    page_no = int(k)
                except Exception:
                    page_no = len(out) + 1
                if isinstance(v, dict):
                    txt = v.get("text") or v.get("extracted_text") or v.get("content") or ""
                else:
                    txt = str(v or "")
                out.append((page_no, txt))
            if out:
                return sorted(out, key=lambda x: x[0])

        if isinstance(pages, list):
            out = []
            for i, item in enumerate(pages, 1):
                if isinstance(item, dict):
                    page_no = item.get("page") or item.get("page_number") or i
                    txt = item.get("text") or item.get("extracted_text") or item.get("content") or ""
                else:
                    page_no, txt = i, str(item or "")
                try:
                    page_no = int(page_no)
                except Exception:
                    page_no = i
                out.append((page_no, txt))
            if out:
                return out

    # Common single-blob full-text field names.
    for key in ("extracted_text", "full_text", "source_text", "text", "content"):
        val = case.get(key)
        if isinstance(val, str) and val.strip():
            return [(1, val)]

    # Legacy serialized/JSON-ish page data.
    for key in ("document", "extracted"):
        val = case.get(key)
        if isinstance(val, str) and val.strip():
            return [(1, val)]

    return []


def search_case_full_text(case, query, max_results=20, source_text=None):
    """Search the complete extracted/source text, never the generated summary.

    ``source_text`` is used by the Telegram/SQLite path because the case row
    itself does not contain ``case_documents.extracted_text``.  This keeps the
    search layer independent from the database while ensuring the live handler
    searches the actual stored document text.
    """
    if isinstance(source_text, str) and source_text.strip():
        return search_text_with_pages(source_text, query, max_results=max_results)
    pages = _full_extracted_pages_from_case(case)
    return search_pages(pages, query, max_results=max_results)


def search_cases_full_text(cases, query, max_results_per_case=10, max_total=20):
    """Search across user's cases using full extracted text only."""
    all_results = []
    for case in cases or []:
        hits = search_case_full_text(case, query, max_results=max_results_per_case)
        if not hits:
            continue
        case_name = (
            case.get("title")
            or case.get("name")
            or case.get("case_name")
            or case.get("filename")
            or "پرونده بدون نام"
        )
        case_id = case.get("id") or case.get("case_id")
        for hit in hits:
            item = dict(hit)
            item["case_name"] = case_name
            item["case_id"] = case_id
            all_results.append(item)
            if len(all_results) >= max_total:
                return all_results
    return all_results



def search_case_documents(documents, query, max_results=40, max_results_per_document=12):
    """Search each authorized case document independently and preserve provenance.

    ``documents`` must already be scoped to one case owned by the requesting
    user (the database accessor enforces this). No generated summaries are
    searched; only extracted source text is considered.
    """
    if not query or not str(query).strip():
        return []
    results = []
    for document in documents or []:
        source = (document.get("extracted_text") or "").strip()
        if not source:
            continue
        hits = search_text_with_pages(
            source, query, max_results=max_results_per_document
        )
        for hit in hits:
            item = dict(hit)
            item["document_id"] = document.get("id")
            item["file_name"] = document.get("file_name") or "سند بدون نام"
            item["page_count"] = document.get("page_count")
            results.append(item)
            if len(results) >= max_results:
                return results
    return results


def format_case_search_results(results, query):
    """Render document-grouped search hits with explicit source provenance."""
    if not results:
        return (
            f"🔎 نتیجه‌ای برای عبارت «{query}» پیدا نشد.\n\n"
            "این جست‌وجو فقط متن استخراج‌شدهٔ اسناد قابل‌دسترسی پرونده را پوشش می‌دهد؛ "
            "اسناد اسکن‌شده یا فاقد متن استخراج‌شده ممکن است در نتایج نباشند."
        )

    groups = {}
    for hit in results:
        key = (hit.get("document_id"), hit.get("file_name") or "سند بدون نام")
        groups.setdefault(key, []).append(hit)

    lines = [
        f"🔎 نتایج جست‌وجو برای: «{query}»",
        f"📌 {len(results)} مورد در {len(groups)} سند پیدا شد.",
        "نتایج بر اساس سند مبدأ تفکیک شده‌اند:",
        "",
    ]
    number = 0
    for (_, file_name), hits in groups.items():
        document_id = hits[0].get("document_id")
        lines.append(f"📄 {file_name}")
        if document_id is not None:
            lines.append(f"شناسه سند: {document_id} | تعداد تطبیق: {len(hits)}")
        else:
            lines.append(f"تعداد تطبیق: {len(hits)}")
        for hit in hits:
            number += 1
            page = hit.get("page")
            page_label = f"صفحه {page}" if page not in (None, "", 0) else "شماره صفحه در دسترس نیست"
            line_no = hit.get("line")
            locator = f"، سطر {line_no}" if line_no else ""
            lines.append(f"\n{number}. 📍 {page_label}{locator}")
            snippet = (hit.get("snippet") or "").strip()
            if snippet:
                lines.append(f"{snippet}")
            else:
                lines.append("متن پیرامونی برای این تطبیق موجود نیست.")
        lines.append("\n────────────────────")

    lines.append(
        "⚠️ نتیجهٔ جست‌وجو صرفاً محل تطبیق در متن استخراج‌شده را نشان می‌دهد؛ "
        "برای استناد، متن سند اصلی را بررسی کنید."
    )
    return "\n".join(lines).strip()

