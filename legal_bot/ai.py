import json, re, requests, time, contextvars
from .ai_usage import record_ai_usage
from .ai_optimizer import compact_messages, estimate_tokens_from_chars
_AI_FEATURE = contextvars.ContextVar("machina_ai_feature", default="unspecified")
_AI_PREFERENCE_UID = contextvars.ContextVar("machina_ai_preference_uid", default=None)
from .config import (
    DEEPSEEK_API_KEY, AI_ENABLED, AI_EXTERNAL_DATA_CONSENT,
    AI_MAX_CHARS, AI_TEXT_MAX_CHARS, AI_BASE_URL, AI_MODEL
)

PAGE_RE = re.compile(r'\[صفحه\s+(\d+)\]')

def _split_page_body(body, capacity, overlap=240):
    """Split oversized page text near a sentence/paragraph boundary.

    A small overlap helps preserve facts that straddle a hard chunk boundary.
    The page marker is added by the caller to every piece so provenance remains
    valid. Overlap is intentionally bounded to keep token usage predictable.
    """
    body=str(body or '')
    if not body:
        return ['']
    capacity=max(1000, int(capacity))
    overlap=max(0, min(int(overlap), capacity // 10))
    pieces=[]; start=0; n=len(body)
    # Prefer paragraph breaks, then sentence punctuation, then whitespace.
    boundary_re=re.compile(r'\n\s*\n|(?<=[.!؟؛])\s+|\s+')
    while start < n:
        end=min(n, start+capacity)
        if end < n:
            floor=start + int(capacity * 0.65)
            candidates=[m.end() for m in boundary_re.finditer(body, floor, end)]
            if candidates:
                end=candidates[-1]
        if end <= start:
            end=min(n,start+capacity)
        piece=body[start:end].strip()
        if piece:
            pieces.append(piece)
        if end >= n:
            break
        next_start=max(start+1, end-overlap)
        # Do not repeatedly begin inside the same whitespace run.
        while next_start < n and body[next_start].isspace():
            next_start += 1
        start=next_start
    return pieces


def _chunks(text, size=8500, max_chunks=16):
    """Page-aware chunks with boundary-aware splits and a hard cost ceiling.

    When the source exceeds the ceiling, retain beginning and ending coverage
    and report truncation to the caller. Every split piece retains its page
    marker, allowing extracted findings to be checked against source pages.
    """
    parts=[p for p in re.split(r'(?=\[صفحه\s+\d+\])', text) if p.strip()]
    chunks=[]; cur=''
    for part in parts:
        if len(part) > size:
            if cur: chunks.append(cur); cur=''
            marker=re.match(r'\[صفحه\s+\d+\]\s*',part)
            prefix=marker.group(0) if marker else ''
            body=part[len(prefix):]
            capacity=max(1000,size-len(prefix))
            chunks.extend(prefix+piece for piece in _split_page_body(body,capacity))
            continue
        if cur and len(cur)+len(part)>size:
            chunks.append(cur); cur=''
        cur+=part
    if cur: chunks.append(cur)
    truncated=len(chunks)>max_chunks
    if truncated:
        if max_chunks <= 1:
            chunks=chunks[:1]
        else:
            head=max_chunks//2
            tail=max_chunks-head
            chunks=chunks[:head]+chunks[-tail:]
    return chunks, truncated

def _call(messages, temperature=0.05):
    feature=_AI_FEATURE.get()
    if not (AI_ENABLED and DEEPSEEK_API_KEY and AI_EXTERNAL_DATA_CONSENT):
        raise RuntimeError('AI disabled, key missing, or external-data consent not enabled')
    optimized_messages, optimization = compact_messages(messages)
    estimated_prompt_tokens = estimate_tokens_from_chars(optimization["after_chars"])
    started=time.monotonic()
    try:
        r=requests.post(
            f'{AI_BASE_URL}/chat/completions',
            headers={'Authorization':f'Bearer {DEEPSEEK_API_KEY}','Content-Type':'application/json'},
            json={'model':AI_MODEL,'messages':optimized_messages,'temperature':temperature},
            timeout=90)
        r.raise_for_status()
        data=r.json()
        content=data['choices'][0]['message']['content'].strip()
        record_ai_usage(feature=feature,model=AI_MODEL,usage=data.get('usage'),latency_ms=int((time.monotonic()-started)*1000),status='success',prompt_chars=optimization['after_chars'],estimated_prompt_tokens=estimated_prompt_tokens,compacted_chars_saved=optimization['saved_chars'])
        return content
    except Exception:
        record_ai_usage(feature=feature,model=AI_MODEL,latency_ms=int((time.monotonic()-started)*1000),status='failed',prompt_chars=optimization['after_chars'],estimated_prompt_tokens=estimated_prompt_tokens,compacted_chars_saved=optimization['saved_chars'])
        raise

def _call_feature(messages, temperature=0.05, feature="unspecified", preference_uid=None):
    """Attach feature metadata and an owner-scoped, allowlisted preference block.

    The UID must come from the authenticated dispatcher, never from prompt data.
    Existing callers that do not supply it retain the legacy prompt unchanged.
    """
    token = _AI_FEATURE.set(str(feature or "unspecified"))
    uid_token = _AI_PREFERENCE_UID.set(preference_uid)
    try:
        prepared = list(messages or [])
        if preference_uid is not None:
            try:
                from .ai_preference_context import load_ai_preference_context
                # Map the internal feature identifier to a narrow preference
                # profile. The feature name is application-controlled, not user input.
                feature_task_map = {
                    "legal_question": "legal_question",
                    "legal_drafting": "legal_drafting",
                    "contract_review": "contract_review",
                    "case_summary": "case_summary",
                    "document_consistency_review": "document_review",
                    "document_structured_extraction": "extraction",
                    "verified_summary": "case_summary",
                    "scan_vision_transcription": "extraction",
                }
                feature_key = str(feature or "").lower()
                preference_task = feature_task_map.get(feature_key, "general")
                if feature_key.startswith("text_assist_"):
                    preference_task = "legal_drafting"
                preference_context = load_ai_preference_context(preference_uid, task=preference_task)
            except Exception:
                preference_context = ""
            if preference_context:
                # Insert after existing system instructions and before user content.
                insert_at = 0
                while insert_at < len(prepared) and prepared[insert_at].get("role") == "system":
                    insert_at += 1
                prepared.insert(insert_at, {"role": "system", "content": preference_context})
        return _call(prepared, temperature=temperature)
    finally:
        _AI_PREFERENCE_UID.reset(uid_token)
        _AI_FEATURE.reset(token)


def _json(text):
    text=text.strip()
    text=re.sub(r'^```(?:json)?\s*|\s*```$','',text,flags=re.I|re.S)
    start=text.find('{')
    if start<0: raise ValueError('AI JSON response not found')
    depth=0; ins=False; esc=False
    for i in range(start,len(text)):
        ch=text[i]
        if ins:
            if esc: esc=False
            elif ch=='\\': esc=True
            elif ch=='"': ins=False
        elif ch=='"': ins=True
        elif ch=='{': depth+=1
        elif ch=='}':
            depth-=1
            if depth==0:
                return json.loads(text[start:i+1])
    raise ValueError('Unbalanced AI JSON')

def _valid_pages(text):
    return set(int(x) for x in PAGE_RE.findall(text))

def _clean_item(item, valid_pages):
    if not isinstance(item, dict): return None
    pages=item.get('source_pages') or item.get('pages') or []
    good=[]
    for p in pages:
        try:
            p=int(str(p).translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹','0123456789')))
            if p in valid_pages: good.append(p)
        except Exception: pass
    # For legal extraction, provenance is mandatory.
    if not good: return None
    item['source_pages']=sorted(set(good))
    item.pop('pages',None)
    return item

def _merge_extracted_results(results):
    """Deterministically merge chunk results without losing successful chunks.

    Only provenance-bearing records are merged. Exact duplicate records are
    collapsed while records with different source pages remain distinct.
    """
    fields=('parties','claims','dates','amounts','obligations',
            'legal_references','key_facts','uncertainties','review_points')
    merged={key:[] for key in fields}
    document_types=[]
    seen={key:set() for key in fields}
    for result in results:
        if not isinstance(result,dict):
            continue
        doc_type=result.get('document_type')
        if isinstance(doc_type,str) and doc_type.strip() and doc_type.strip() not in document_types:
            document_types.append(doc_type.strip()[:200])
        for key in fields:
            values=result.get(key) or []
            if not isinstance(values,list):
                continue
            for item in values:
                if not isinstance(item,dict) or not item.get('source_pages'):
                    continue
                # Stable JSON key avoids dropping same text found on different pages.
                marker=json.dumps(item,ensure_ascii=False,sort_keys=True,separators=(',',':'))
                if marker not in seen[key]:
                    seen[key].add(marker)
                    merged[key].append(item)
    if document_types:
        merged['document_type']=document_types[0] if len(document_types)==1 else '؛ '.join(document_types[:4])
    return merged


def _validate_result(result, text):
    if not isinstance(result,dict): return {}
    valid=_valid_pages(text)
    list_fields=['parties','claims','dates','amounts','obligations',
                 'legal_references','key_facts','uncertainties','review_points']
    out={}
    if isinstance(result.get('document_type'),str): out['document_type']=result['document_type'][:200]
    for key in list_fields:
        vals=result.get(key) or []
        cleaned=[]
        for x in vals:
            if isinstance(x,dict):
                y=_clean_item(dict(x),valid)
                if y: cleaned.append(y)
            # Scalar AI claims are discarded because they cannot carry provenance.
        out[key]=cleaned[:20]
    return out

def _dedupe_exact_paragraphs_per_page(text):
    """Remove only exact repeated paragraphs within the same page.

    Page markers are preserved and identical text on different pages is kept,
    because repetition across pages can itself be evidentially meaningful.
    This is a deterministic token-saving step; it does not summarize or rewrite.
    """
    text = str(text or '')
    parts = re.split(r'(?=\[صفحه\s+\d+\])', text)
    output = []
    removed = 0
    for part in parts:
        if not part.strip():
            continue
        marker = re.match(r'(\[صفحه\s+\d+\]\s*)', part)
        prefix = marker.group(1) if marker else ''
        body = part[len(prefix):]
        paragraphs = re.split(r'(\n\s*\n)', body)
        seen = set()
        kept = []
        for item in paragraphs:
            if not item or re.fullmatch(r'\n\s*\n', item):
                kept.append(item)
                continue
            normalized = re.sub(r'\s+', ' ', item).strip()
            if normalized and normalized in seen:
                removed += 1
                continue
            if normalized:
                seen.add(normalized)
            kept.append(item)
        output.append(prefix + ''.join(kept))
    return ''.join(output), removed


def _query_terms(text):
    stop = {'برای','است','این','آن','که','با','از','در','را','به','چه','چگونه','آیا','یک','های','شود','می‌شود'}
    words = re.findall(r'[\u0600-\u06ff]{2,}', str(text or ''))
    return {w for w in words if w not in stop}


def _rank_local_legal_records(records, question, limit=5):
    """Rank local legal records cheaply using lexical overlap, no AI call."""
    terms = _query_terms(question)
    scored = []
    for index, record in enumerate(records or []):
        if not isinstance(record, dict):
            continue
        searchable = ' '.join(str(record.get(k) or '') for k in
                              ('law','title','article','ruling_number','consultation_number',
                               'clean_text','ntext','text','question'))
        overlap = len(terms & _query_terms(searchable))
        scored.append((overlap, -index, record))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [x[2] for x in scored[:max(1, int(limit))] if x[0] > 0] or list(records or [])[:max(1, int(limit))]


def structured_analysis(text, *, preference_uid=None):
    if not (AI_ENABLED and DEEPSEEK_API_KEY and AI_EXTERNAL_DATA_CONSENT):
        return {}
    text=str(text or '')
    if not text.strip(): return {}
    text, locally_removed_paragraphs = _dedupe_exact_paragraphs_per_page(text)
    # Let the page-aware chunker select broad coverage from the complete
    # extracted text. Slicing here would discard the entire tail before the
    # chunker's head/tail coverage strategy can run.
    hard_truncated=False
    chunks,chunk_truncated=_chunks(text)
    extracted=[]
    failed=0
    for idx,ch in enumerate(chunks,1):
        prompt=f"""فقط از متن همین بخش استخراج کن. هیچ واقعیت، عدد، تاریخ، نام، ماده قانونی یا نتیجه حقوقی را حدس نزن.
شماره صفحات با [صفحه N] مشخص شده و برای هر مورد source_pages الزامی است.
اگر چیزی مبهم است در uncertainties بگذار.
خروجی فقط JSON معتبر:
{{"document_type":"","parties":[{{"name":"","role":"","source_pages":[]}}],
"claims":[{{"claim":"","source_pages":[]}}],
"dates":[{{"value":"","event":"","source_pages":[]}}],
"amounts":[{{"value":"","context":"","source_pages":[]}}],
"obligations":[{{"text":"","source_pages":[]}}],
"legal_references":[{{"reference":"","source_pages":[]}}],
"key_facts":[{{"fact":"","source_pages":[]}}],
"uncertainties":[{{"item":"","source_pages":[]}}]}}
بخش {idx} از {len(chunks)}:
{ch}"""
        try:
            raw=_json(_call_feature([
                {'role':'system','content':'فقط JSON معتبر و فارسی. هیچ اطلاعاتی خارج از متن اضافه نکن.'},
                {'role':'user','content':prompt}], feature='document_structured_extraction', preference_uid=preference_uid))
            cleaned=_validate_result(raw,ch)
            if cleaned: extracted.append(cleaned)
        except Exception:
            failed+=1

    if not extracted:
        return {'ai_used':False,'ai_error':'AI extraction failed','ai_truncated':hard_truncated or chunk_truncated}

    # Merge chunk outputs locally. A second model call used to synthesize the
    # same extracted records added cost and latency while often repeating the
    # deterministic merge. Provenance validation has already happened per chunk;
    # keep the complete local merge instead of paying for a redundant synthesis.
    result=_merge_extracted_results(extracted)
    result['ai_used']=True
    result['ai_truncated']=bool(hard_truncated or chunk_truncated)
    result['ai_failed_chunks']=failed
    result['ai_chunks_processed']=len(extracted)
    result['ai_synthesis_calls_saved']=1
    result['ai_duplicate_paragraphs_removed']=locally_removed_paragraphs
    return result


def ask_ai_question(question, case_summary='', standard_prompt='', *, preference_uid=None):
    """Send a user question to the external AI only after explicit AI-button use.

    Optional local case summary and standard legal prompt are included only when
    the user selected them. The full case text is never sent by this path.
    """
    question=str(question or '').strip()
    if not question: raise ValueError('سؤال خالی است.')
    if len(question)>AI_TEXT_MAX_CHARS: raise ValueError(f'سؤال بیش از حد مجاز است. سقف این ابزار {AI_TEXT_MAX_CHARS} نویسه است.')
    standard_prompt=str(standard_prompt or '').strip()
    case_summary=str(case_summary or '').strip()
    user_parts=['سؤال کاربر:\n'+question]
    if standard_prompt:
        user_parts.append('پرامپت استاندارد:\n'+standard_prompt)
    if case_summary:
        user_parts.append('خلاصه محلی پرونده (فقط زمینه کمکی؛ منبع اصلی پرونده نیست):\n'+case_summary[:12000])
    # Conservative local-source retrieval: only activate when the user explicitly
    # names Iran/Iranian law. This does not fetch live sources and never upgrades
    # a registry label into a claim that the law is current or applicable.
    iran_scope = bool(re.search(r'ایران|ایرانی|قانون مدنی|قانون مجازات اسلامی|قانون تجارت ایران|قانون کار ایران', question, re.I))
    if iran_scope:
        try:
            from .laws import search_legal_research
            records = search_legal_research(question, limit=12)
            records = _rank_local_legal_records(records, question, limit=5)
            source_lines = []
            for rec in records:
                title = str(rec.get('law') or rec.get('title') or '').strip()
                locator = str(rec.get('article') or rec.get('ruling_number') or rec.get('consultation_number') or '').strip()
                excerpt = str(rec.get('clean_text') or rec.get('ntext') or rec.get('text') or rec.get('question') or '').strip()
                if not title and not excerpt:
                    continue
                citation = rec.get('citation') if isinstance(rec.get('citation'), dict) else {}
                status = str(citation.get('verification_label') or rec.get('verification_label') or 'وضعیت تأیید نامشخص')
                urls = citation.get('source_urls') or rec.get('source_urls') or []
                line = f'منبع محلی: {title}' + (f'، محل: {locator}' if locator else '') + f'، وضعیت ثبت‌شده: {status}'
                if urls:
                    line += '، نشانی ثبت‌شده: ' + '، '.join(str(u) for u in urls[:2])
                if excerpt:
                    line += '\nگزیدهٔ متن موجود: ' + re.sub(r'\s+', ' ', excerpt)[:900]
                source_lines.append(line)
            if source_lines:
                user_parts.append(
                    'نتایج بازیابی محلی زیر فقط سرنخ و متن موجود در مخزن محلی‌اند؛ '
                    'ترتیب نتایج دلیل حقوقی بودن یا جاری بودن منبع نیست. وضعیت و گزیده را دقیق گزارش کن، '
                    'از آن‌ها فقط در حدی استناد کن که متن واقعاً پشتیبانی می‌کند و اگر وضعیت/متن کافی نیست صریحاً بگو:\n'
                    + '\n\n'.join(source_lines[:5])
                )
        except Exception:
            # Retrieval failure must not block the user's legal question.
            pass
    prompt='\n\n---\n\n'.join(user_parts)
    system=(
        'دستیار حقوقی فارسی برای پاسخ اولیه به پرسش‌های عمومی هستی؛ پاسخ تو اطلاعات اولیه است، نه تصمیم قطعی درباره پرونده. '
        'ابتدا مسئله حقوقی و هدف کاربر را تشخیص بده و پاسخ را روشن، حرفه‌ای، کم‌حاشیه و متناسب با پیچیدگی سؤال بنویس. '
        'اگر کشور یا حوزه قضایی از سؤال روشن نیست و پاسخ به آن وابسته است، قانون کشور خاصی را فرض نکن. در صورت امکان یک توضیح کلیِ صریحاً غیرمختص به حوزه قضایی بده و مهم‌ترین سؤال تکمیلی را بپرس. '
        'اگر یک واقعیت ضروری مانند نوع قرارداد، تاریخ ابلاغ، سمت کاربر یا مرحله رسیدگی مفقود است، نتیجه قطعی نده؛ فقط سؤال‌های تکمیلی تعیین‌کننده را مطرح کن و از پرسش‌باران کاربر بپرهیز. '
        'هیچ ماده قانونی، شماره رأی، تاریخ، مهلت، مبلغ، نقل‌قول یا منبعی را جعل نکن. نقل دقیق شماره ماده یا رأی فقط وقتی مجاز است که متن یا منبع قابل اتکا در ورودی موجود باشد و با ادعا مرتبط باشد. '
        'وجود یک منبع یا تطبیق عنوان آن، به‌تنهایی ثابت نمی‌کند که منبع ادعا را پشتیبانی می‌کند. اگر منبعی در اختیار نیست، این محدودیت را آشکار کن و استناد دقیق را برای بررسی از منبع رسمی علامت بزن. '
        'قانون جاری یا آخرین اصلاحات را بدون منبع به‌روز تأییدشده، قطعی و به‌روز معرفی نکن؛ تاریخ‌حساس بودن پاسخ را صریح بگو. '
        'واقعیت‌های گفته‌شده از سوی کاربر را از ادعاها، فرض‌ها و تحلیل خودت جدا نگه دار. اگر دو برداشت محتمل است، آن‌ها را مشروط توضیح بده و بی‌دلیل یکی را انتخاب نکن. '
        'ساختار پیشنهادی: پاسخ کوتاه؛ توضیح و شرایط مؤثر؛ اطلاعات یا منبعی که هنوز باید بررسی شود؛ گام بعدی عملی، فقط اگر مفید باشد. برای سؤال ساده از این قالب به‌صورت مصنوعی و طولانی استفاده نکن. '
        'مهلت قانونی، خطر فوری یا اقدام برگشت‌ناپذیر را حدس نزن؛ اگر ممکن است فوریت وجود داشته باشد، از کاربر بخواه تاریخ و سند مرتبط را بررسی کند و سریعاً از مرجع رسمی یا متخصص صلاحیت‌دار کمک بگیرد. '
        'نتیجه دعوا را تضمین نکن و راهنمایی را جایگزین مشاوره تخصصی یا بررسی منابع رسمی ندان.'
    )
    return _call_feature([{'role':'system','content':system},{'role':'user','content':prompt}],temperature=0.1, feature='legal_question', preference_uid=preference_uid)

def _sample_case_text(text, max_chars):
    """Select bounded beginning, middle and ending excerpts without losing the tail.

    The previous implementation sliced the assembled string after adding labels,
    which could silently cut off the ending excerpt. This version reserves space
    for every marker before allocating excerpt budgets.
    """
    text = str(text or '').strip()
    max_chars = max(1, int(max_chars))
    if len(text) <= max_chars:
        return text, False

    gap = "\n\n[بخش‌هایی از متن برای کنترل هزینه ارسال نشده‌اند]\n\n"
    middle_label = "[گزیده میانی متن اصلی]\n"
    ending_label = "[گزیده پایانی متن اصلی]\n"
    overhead = len(gap) * 2 + len(middle_label) + len(ending_label)
    excerpt_budget = max_chars - overhead
    if excerpt_budget < 3:
        return text[:max_chars], True

    first = max(1, excerpt_budget // 3)
    middle = max(1, excerpt_budget // 3)
    last = max(1, excerpt_budget - first - middle)

    # Keep the three windows disjoint and in their original document order.
    start_text = text[:first]
    middle_start = max(first, (len(text) - last - middle) // 2)
    middle_start = min(middle_start, max(first, len(text) - last - middle))
    middle_text = text[middle_start:middle_start + middle]
    end_start = max(middle_start + len(middle_text), len(text) - last)
    end_text = text[end_start:]
    if len(end_text) > last:
        end_text = end_text[-last:]

    sampled = (
        start_text + gap + middle_label + middle_text +
        gap + ending_label + end_text
    )
    # Defensive handling for unusually short source text or unicode edge cases.
    if len(sampled) > max_chars:
        sampled = sampled[:max_chars]
    return sampled, True


def summarize_case_for_lawyer(extracted_text, local_summary='', *, preference_uid=None):
    """Produce a compact, source-conscious case summary in one explicit AI call.

    Only locally extracted text is accepted; original documents/images are never
    read or uploaded here. The caller must enforce external-data consent and quota.
    """
    if not (AI_ENABLED and DEEPSEEK_API_KEY and AI_EXTERNAL_DATA_CONSENT):
        raise RuntimeError('AI disabled, key missing, or external-data consent not enabled')
    text = str(extracted_text or '').strip()
    if not text:
        raise ValueError('متن استخراج‌شده پرونده خالی است.')
    # Keep the request bounded for predictable cost. The local analysis still
    # runs on the complete extracted text; the AI receives only a compact sample.
    max_input = min(9000, max(1000, AI_TEXT_MAX_CHARS - 2500))
    text, truncated = _sample_case_text(text, max_input)
    local_summary = str(local_summary or '').strip()[:3500]
    prompt = f"""وظیفه: گزارش خلاصه و کاربردی از پرونده حقوقی تهیه کن.
قواعد الزامی:
- فقط از متن استخراج‌شده و خلاصه محلی زیر استفاده کن؛ هیچ واقعیت، نام، تاریخ، مبلغ، ادعا، ماده قانونی یا شماره رأی نساز.
- تفاوت «واقعیت مندرج در سند»، «ادعای یکی از طرفین» و «برداشت/تحلیل» را در هر بخش روشن نگه دار.
- برای هر نکته مهم، شاهد متنی کوتاه یا صفحه را فقط اگر در ورودی موجود است ذکر کن؛ شماره صفحه جدید حدس نزن.
- اگر دو داده با هم ناسازگارند، هر دو را جداگانه گزارش کن؛ خودسرانه یکی را درست انتخاب نکن.
- بین «در متن ارائه‌شده یافت نشد» و «وجود ندارد» تفاوت بگذار.
- نقاط قوت/ضعف را فقط به‌عنوان محور بررسی مبتنی بر شواهد بیان کن؛ نتیجه دعوا یا اعتبار نهایی دلیل را قطعی اعلام نکن.
- نبودن یک مورد در متن استخراج‌شده به معنی نبودن آن در پرونده واقعی نیست.
- اگر اطلاعات کافی نیست، آن را در بخش «ابهام‌ها و اطلاعات موردنیاز» بگو.
- نتیجه حقوقی قطعی یا تضمین نتیجه دعوا نده.
- فارسی حرفه‌ای و ساده، بدون مقدمه طولانی؛ حداکثر حدود 650 کلمه.
قالب دقیق:
📄 خلاصه پرونده
۱) موضوع و وضعیت قابل تشخیص
۲) طرفین و نقش‌ها
۳) وقایع و تاریخ‌های مهم
۴) خواسته‌ها و ادعاهای صریح
۵) مدارک/نکات مستند مهم
۶) ابهام‌ها و اطلاعات موردنیاز
۷) نقاط قوت و ضعف مستند (با توضیح شاهد و محدودیت)
۸) اقدامات بعدی پیشنهادی برای بررسی
اگر بخشی شواهد کافی ندارد، بنویس «در متن ارائه‌شده مشخص نیست».

خلاصه محلی استخراج‌شده:
{local_summary or 'خلاصه محلی جداگانه موجود نیست.'}

متن استخراج‌شده پرونده (ممکن است نمونه‌ای محدود از متن باشد):
{text}
"""
    result = _call_feature([
        {'role': 'system', 'content': 'تو دستیار تحلیل اسناد حقوقی فارسی هستی. به متن ورودی وفادار بمان و عدم قطعیت را آشکار کن.'},
        {'role': 'user', 'content': prompt},
    ], temperature=0.1, feature='case_summary', preference_uid=preference_uid)
    if not result:
        raise RuntimeError('خروجی خلاصه‌سازی خالی است.')
    if truncated:
        result += '\n\n⚠️ یادداشت پوشش: به‌دلیل محدودیت هزینه، فقط بخش‌هایی از متن استخراج‌شده برای خلاصه‌سازی هوش مصنوعی ارسال شد؛ تحلیل محلی پرونده کل متن قابل استخراج را بررسی کرده است.'
    return result


def text_assist(text, task, *, preference_uid=None):
    text=str(text or '').strip()
    if not text: raise ValueError('متنی برای پردازش وجود ندارد.')
    if len(text)>AI_TEXT_MAX_CHARS: raise ValueError(f'متن بیش از حد مجاز است. سقف این ابزار {AI_TEXT_MAX_CHARS} نویسه است.')
    tasks={
      'formal':'متن را رسمی، روان و مناسب نگارش حقوقی بازنویسی کن؛ معنا، ادعا، عدد، تاریخ و استناد جدید اضافه نکن.',
      'short':'متن را کوتاه و منسجم کن؛ هیچ واقعیت یا نکته‌ای حذف نکن مگر تکراری باشد.',
      'bullets':'متن را به bullet pointهای کوتاه و روشن تبدیل کن؛ اطلاعات جدید اضافه نکن.',
      'title':'حداکثر 5 عنوان مناسب برای این متن پیشنهاد بده؛ فقط عنوان‌ها را بنویس.',
      'structure':'برای این متن یک ساختار منطقی پیشنهادی با تیترهای کوتاه بده؛ متن حقوقی جدید یا استناد جدید نساز.',
      'rewrite':'متن را روان‌تر و منسجم‌تر بازنویسی کن؛ محتوا و موضع نویسنده را تغییر نده.',
      'legal_question':'به سؤال حقوقی کاربر پاسخ آموزشی و محتاطانه بده. اگر برای پاسخ قطعی به قانون، تاریخ یا جزئیات پرونده نیاز است و در متن سؤال موجود نیست، صریحاً بگو اطلاعات کافی نیست. ماده قانون، رأی یا واقعیت را حدس نزن و منبع جعلی نساز. پاسخ جایگزین مشاوره حقوقی تخصصی نیست.'}
    if task not in tasks: raise ValueError('نوع عملیات نامعتبر است.')
    prompt=f"""تو یک دستیار نگارشی هستی، نه مشاور حقوقی. {tasks[task]}
اگر متن مبهم است، ابهام را حفظ کن. هیچ ماده قانون، رأی، واقعیت یا منبعی اختراع نکن.
متن:
{text}"""
    return _call_feature([{'role':'system','content':'پاسخ فارسی، دقیق و فقط بر اساس متن ورودی باشد.'},{'role':'user','content':prompt}],temperature=0.15, feature='text_assist_'+task, preference_uid=preference_uid)


def recover_text_from_image(path, page_label=None):
    """Optional exception path for unreadable scans. Disabled unless explicitly configured.
    Uses a vision-capable OpenAI-compatible endpoint and asks for transcription only."""
    from .config import AI_VISION_ENABLED, AI_VISION_MODEL, AI_RECOVERY_MAX_PAGES
    if not (AI_VISION_ENABLED and DEEPSEEK_API_KEY and AI_EXTERNAL_DATA_CONSENT):
        raise RuntimeError('AI vision recovery is disabled')
    model=AI_VISION_MODEL or AI_MODEL
    import base64
    from pathlib import Path
    data=Path(path).read_bytes()
    mime='image/png' if str(path).lower().endswith('.png') else 'image/jpeg'
    b64=base64.b64encode(data).decode('ascii')
    prompt=("فقط متن قابل مشاهده در تصویر را رونویسی کن. هیچ اصلاح حقوقی، حدس، خلاصه یا تکمیل انجام نده. "
            "اعداد، تاریخ‌ها، شماره پرونده و مواد قانونی را دقیقاً همان‌طور که دیده می‌شوند بنویس. "
            "اگر بخشی خوانا نیست [نامشخص] بنویس. خروجی فقط متن فارسی و بدون مقدمه باشد.")
    optimized_messages, optimization = compact_messages(messages)
    estimated_prompt_tokens = estimate_tokens_from_chars(optimization["after_chars"])
    started=time.monotonic()
    try:
        r=requests.post(
            f'{AI_BASE_URL}/chat/completions',
            headers={'Authorization':f'Bearer {DEEPSEEK_API_KEY}','Content-Type':'application/json'},
            json={'model':model,'messages':[{'role':'user','content':[
                {'type':'text','text':prompt},
                {'type':'image_url','image_url':{'url':f'data:{mime};base64,{b64}'}}
            ]}],'temperature':0}, timeout=120)
        r.raise_for_status()
        data=r.json()
        record_ai_usage(feature='scan_vision_transcription',model=model,usage=data.get('usage'),latency_ms=int((time.monotonic()-started)*1000),status='success')
        content=data['choices'][0]['message']['content']
    except Exception:
        record_ai_usage(feature='scan_vision_transcription',model=model,latency_ms=int((time.monotonic()-started)*1000),status='failed')
        raise
    if isinstance(content,list):
        content=''.join(x.get('text','') for x in content if isinstance(x,dict))
    return str(content).strip()


_DIGITS_RE = re.compile(r'[0-9۰-۹]+(?:[,.،/-][0-9۰-۹]+)*')

def _numeric_tokens(text):
    return [x for x in _DIGITS_RE.findall(str(text or '')) if any(c.isdigit() or c in '۰۱۲۳۴۵۶۷۸۹' for c in x)]

def _numbers_are_source_safe(candidate, source):
    """Reject generated summaries containing a number absent from source."""
    src=str(source or '').translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹','0123456789'))
    for tok in _numeric_tokens(candidate):
        norm=tok.translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹','0123456789'))
        if norm not in src:
            return False
    return True

def verified_summary(text, max_items=16, *, preference_uid=None):
    """Create a source-grounded summary; AI output is accepted only after validation."""
    from .analysis import _snippets, _rank_summary_sentences
    from .text_guard import normalize_output
    text=str(text or '').strip()
    if not text: return []
    snippets=[{'page':pg,'text':st} for pg,st in _snippets(text,limit=36)]
    local=_rank_summary_sentences(text,snippets,limit=max_items)
    fallback=[{'text':normalize_output(x['text']),'page':x.get('page')} for x in local]
    if not (AI_ENABLED and DEEPSEEK_API_KEY and AI_EXTERNAL_DATA_CONSENT):
        return fallback
    source='\n'.join(f'[صفحه {x.get("page")}] {x["text"]}' for x in local)
    prompt=f'''فقط بر اساس جملات منبع زیر یک خلاصه کوتاه تهیه کن.
قواعد: هیچ واقعیت یا عدد جدید نساز؛ هر عدد، تاریخ، مبلغ و شماره را دقیقاً همان‌طور که در منبع آمده کپی کن؛ اگر درباره موردی مطمئن نیستی آن را حذف کن؛ هر مورد source_pages داشته باشد؛ حداکثر {max_items} مورد.
خروجی فقط JSON: {{"items":[{{"text":"","source_pages":[]}}]}}

منبع:
{source}'''
    try:
        raw=_json(_call_feature([
            {'role':'system','content':'خلاصه‌ساز محافظه‌کار اسناد حقوقی؛ تغییر اعداد و تاریخ‌ها ممنوع.'},
            {'role':'user','content':prompt}],temperature=0.0,feature='verified_summary', preference_uid=preference_uid))
        items=raw.get('items') if isinstance(raw,dict) else None
        if not isinstance(items,list): return fallback
        valid_pages={x.get('page') for x in local if x.get('page') is not None}
        out=[]
        for item in items[:max_items]:
            if not isinstance(item,dict) or not isinstance(item.get('text'),str): continue
            pages=[]
            for pg in item.get('source_pages') or []:
                try:
                    pg=int(str(pg).translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹','0123456789')))
                    if pg in valid_pages: pages.append(pg)
                except Exception: pass
            txt=normalize_output(item['text'])
            if not pages or not txt or not _numbers_are_source_safe(txt,source):
                return fallback
            out.append({'text':txt,'page':pages[0],'source_pages':sorted(set(pages))})
        return out if out else fallback
    except Exception:
        return fallback


def _guard_draft_source_markers(result, valid_source_ids):
    """Flag source markers that do not correspond to supplied legal sources.

    This is a narrow integrity guard: it does not prove that a cited source
    supports the surrounding sentence, but prevents an unknown [S<number>]
    marker from looking like a verified reference.
    """
    result = str(result or '').strip()
    if not result:
        return result
    valid = {str(x) for x in valid_source_ids}
    invalid = []
    pattern = re.compile(r'\[S(\d+)\]', re.I)
    def replace(match):
        number = match.group(1)
        if number in valid:
            return match.group(0)
        invalid.append(number)
        return '[ارجاع منبع نامعتبر؛ نیازمند بررسی]'
    result = pattern.sub(replace, result)
    if invalid:
        result += (
            '\n\n⚠️ کنترل استناد: یک یا چند شناسه منبع در خروجی با منابع '
            'ارائه‌شده تطبیق نداشت و علامت‌گذاری شد. پیش از استفاده، همه استنادها '
            'و پشتیبانی هر ادعا با متن اصلی منبع بررسی شوند.'
        )
    return result


def draft_legal_brief(facts, brief_type, stage, sources=None, style='رسمی و حرفه‌ای', *, preference_uid=None):
    """Source-grounded legal brief draft; authorities are limited to supplied sources."""
    if not (AI_ENABLED and DEEPSEEK_API_KEY and AI_EXTERNAL_DATA_CONSENT):
        raise RuntimeError('AI برای لایحه‌نویسی فعال نیست.')
    facts=str(facts or '').strip()
    if not facts:
        raise ValueError('شرح پرونده خالی است.')
    if len(facts)>AI_TEXT_MAX_CHARS:
        raise ValueError(f'شرح پرونده بیش از سقف مجاز {AI_TEXT_MAX_CHARS} نویسه است.')
    packed=[]
    valid_source_ids=[]
    # Rank local authorities against the lawyer's fact narrative before packing.
    # This is lexical filtering only; it never changes the authority text.
    source_candidates=[]
    fact_terms=_query_terms(facts)
    for original_index,x in enumerate((sources or [])[:20],1):
        if not isinstance(x,dict):
            continue
        authority=x.get('law') or x.get('title') or 'منبع حقوقی'
        article=x.get('article') or x.get('ruling_number') or ''
        source_text=str(x.get('text') or x.get('clean_text') or '').strip()
        searchable=f'{authority} {article} {source_text}'
        score=len(fact_terms & _query_terms(searchable))
        source_candidates.append((score,-original_index,original_index,authority,article,source_text))
    source_candidates.sort(key=lambda row:(row[0],row[1]),reverse=True)
    selected_sources=source_candidates[:5]
    for _,__,original_index,authority,article,source_text in selected_sources:
        if not source_text:
            continue
        source_id=str(len(valid_source_ids)+1)
        valid_source_ids.append(source_id)
        excerpt=source_text[:1400]
        if len(source_text)>1400:
            excerpt += '\n[گزیده محدودشده برای کنترل هزینه؛ متن کامل منبع باید جداگانه بررسی شود]'
        packed.append(f'[S{source_id}] {authority} {article}\n{excerpt}')
    source_pack='\n\n'.join(packed) or 'هیچ منبع حقوقی بازیابی‌شده‌ای در اختیار نیست.'
    prompt=f'''یک پیش‌نویس لایحه حقوقی فارسی تهیه کن. تو دستیار نگارش هستی و حق ساختن قانون، ماده، رأی، تاریخ، شماره پرونده یا واقعیت جدید را نداری.
نوع لایحه: {brief_type}
مرحله رسیدگی: {stage}
سبک: {style}

واقعیات ارائه‌شده توسط وکیل:
{facts}

منابع حقوقی مجاز برای استناد:
{source_pack}

قواعد:
1) فقط به منابع [S1] و مانند آن استناد کن و شماره ماده/رأی را دقیقاً از همان منبع بردار.
2) اگر منبع کافی برای ادعایی وجود ندارد، عبارت «نیازمند بررسی منبع» را بیاور و حدس نزن.
3) واقعیت پرونده را از مستند قانونی و تحلیل احتمالی جدا نگه دار.
4) ساختار: عنوان، خطاب، موضوع، مقدمه، شرح مختصر وقایع، دفاعیات و استدلال‌ها، مستندات، نتیجه و خواسته.
5) نتیجه پرونده را تضمین نکن و نبود یک مدرک در ورودی را دلیل نبود آن در پرونده واقعی ندان.
6) در پایان «موارد نیازمند بازبینی وکیل» را با ابهامات، استنادات نیازمند تطبیق و مدارک احتمالی بیاور.
7) کنار هر استناد قانونی شناسه منبع مثل [S1] را درج کن؛ فقط شناسه‌هایی را به‌کار ببر که در فهرست منابع بالا وجود دارند.
8) اگر منبعی وجود ندارد، استناد قانونی نساز و نیاز به بررسی منبع را صریح بنویس.
9) هر ادعای مهم را به واقعیت ارائه‌شده یا منبع مشخص وصل کن؛ اگر اتصال قابل احراز نیست، آن را به‌عنوان نکته نیازمند بررسی علامت بزن.
'''
    raw_result = _call_feature([
        {'role':'system','content':'دستیار نگارش حقوقی محافظه‌کار و منبع‌محور هستی. هیچ منبع یا واقعیتی را اختراع نکن.'},
        {'role':'user','content':prompt}
    ],temperature=0.1,feature='legal_drafting', preference_uid=preference_uid)
    return _guard_draft_source_markers(raw_result, valid_source_ids)


def _normalize_evidence_quote(value):
    """Normalize harmless formatting differences before exact-source checks."""
    import unicodedata
    value = unicodedata.normalize('NFC', str(value or ''))
    value = value.translate(str.maketrans({'ي':'ی', 'ى':'ی', 'ك':'ک', 'ـ':None}))
    value = value.translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789'))
    return re.sub(r'\s+', ' ', value).strip()


def _validated_review_findings(payload, source_text):
    """Keep only findings whose two quoted witnesses occur in supplied text."""
    if not isinstance(payload, dict) or not isinstance(payload.get('findings'), list):
        return []
    source = _normalize_evidence_quote(source_text)
    findings = []
    allowed_types = {'تناقض احتمالی', 'ابهام', 'نیازمند بررسی'}
    allowed_importance = {'زیاد', 'متوسط', 'کم'}
    for item in payload['findings'][:6]:
        if not isinstance(item, dict):
            continue
        q1 = str(item.get('quote1') or '').strip()
        q2 = str(item.get('quote2') or '').strip()
        n1, n2 = _normalize_evidence_quote(q1), _normalize_evidence_quote(q2)
        # Reject empty, very short, duplicate or unsupported quotations.
        if len(n1) < 8 or len(n2) < 8 or n1 == n2 or n1 not in source or n2 not in source:
            continue
        topic = re.sub(r'\s+', ' ', str(item.get('topic') or 'موضوع نیازمند بررسی')).strip()[:160]
        kind = str(item.get('type') or 'نیازمند بررسی').strip()
        if kind not in allowed_types:
            kind = 'نیازمند بررسی'
        importance = str(item.get('importance') or 'نامشخص').strip()
        if importance not in allowed_importance:
            importance = 'نامشخص'
        action = re.sub(r'\s+', ' ', str(item.get('action') or 'دو بخش در اصل اسناد تطبیق داده شوند.')).strip()[:300]
        findings.append({'topic': topic, 'type': kind, 'quote1': q1[:500], 'quote2': q2[:500],
                         'importance': importance, 'action': action})
    return findings


def review_case_contradictions(extracted_text, local_report='', *, preference_uid=None):
    """Review possible contradictions using source-validated verbatim quotes.

    The model returns structured candidates. A local verifier then requires both
    short quoted witnesses to occur in the exact text supplied to the model.
    Findings remain review suggestions, not factual rulings.
    """
    if not (AI_ENABLED and DEEPSEEK_API_KEY and AI_EXTERNAL_DATA_CONSENT):
        raise RuntimeError('AI disabled, key missing, or external-data consent not enabled')
    text = str(extracted_text or '').strip()
    if not text:
        raise ValueError('متن استخراج‌شده برای بررسی وجود ندارد')
    max_input = min(6500, max(1200, AI_TEXT_MAX_CHARS - 1800))
    truncated = len(text) > max_input
    if truncated:
        head = int(max_input * 0.65)
        tail = max_input - head
        text = text[:head] + '\n\n[بخش‌هایی از متن برای کنترل هزینه ارسال نشده‌اند]\n\n' + text[-tail:]
    prompt = f"""تو دستیار بررسی اولیه اسناد حقوقی هستی. فقط مواردی را گزارش کن که دو عبارت یا داده مشخص در متن، احتمال تعارض واقعی داشته باشند.
قواعد قطعی:
- فقط JSON معتبر با ساختار {{"findings":[{{"topic":"...","type":"تناقض احتمالی یا ابهام یا نیازمند بررسی","quote1":"نقل‌قول عین متن","quote2":"نقل‌قول عین متن","importance":"زیاد یا متوسط یا کم","action":"اقدام پیشنهادی"}}]}} برگردان؛ بیرون JSON هیچ متنی ننویس.
- برای هر مورد، دو نقل‌قول کوتاه و عیناً موجود در متن بیاور؛ اگر دو شاهد قابل نقل‌قول نداری، مورد را گزارش نکن.
- هیچ واقعیت، تاریخ، مبلغ، نام، شماره صفحه یا استناد نساز.
- تفاوتی که ممکن است ناشی از زمان، مرحله، طرف یا موضوع متفاوت باشد را «نیازمند بررسی» بنام، نه تناقض قطعی.
- درباره اینکه کدام عبارت درست است تصمیم نگیر. موارد تکراری، حدس‌ها و توصیه‌های کلی را حذف کن.
- حداکثر ۶ مورد. اگر مورد مستند پیدا نکردی، {{"findings":[]}} برگردان.

گزارش بررسی محلی اولیه (زمینه کمکی، نه حقیقت قطعی):
{str(local_report or 'گزارش محلی موجود نیست')[:1800]}

متن استخراج‌شده پرونده:
{text}

یادآوری: این بررسی اولیه است و جایگزین تطبیق اصل اسناد یا نظر وکیل نیست."""
    raw_result = _call_feature([
        {'role':'system','content':'بررسی‌گر محافظه‌کار اسناد حقوقی؛ وفاداری دقیق به شواهد، بدون جعل. خروجی فقط JSON معتبر باشد.'},
        {'role':'user','content':prompt},
    ], temperature=0.0, feature='document_consistency_review', preference_uid=preference_uid)
    try:
        payload = _json(str(raw_result or ''))
        findings = _validated_review_findings(payload, text)
    except (ValueError, TypeError, json.JSONDecodeError):
        findings = []
    if findings:
        lines = []
        for i, item in enumerate(findings, 1):
            lines.append(
                f"{i}. موضوع: {item['topic']} | نوع: {item['type']} | اهمیت: {item['importance']}\n"
                f"   شاهد اول (تطبیق‌شده با متن ورودی): «{item['quote1']}»\n"
                f"   شاهد دوم (تطبیق‌شده با متن ورودی): «{item['quote2']}»\n"
                f"   اقدام پیشنهادی: {item['action']}"
            )
        result = '\n\n'.join(lines)
    else:
        result = 'در متن بررسی‌شده، موردی با دو شاهد متنی قابل‌تأیید از خروجی مدل به دست نیامد. این نتیجه به معنی نبود تناقض در کل پرونده نیست.'
    if truncated:
        result += '\n\n⚠️ یادداشت پوشش: برای کنترل هزینه فقط بخش‌هایی از متن بررسی شد؛ این گزارش بررسی کامل همه اسناد نیست.'
    return '🔎 بررسی تکمیلی ایرادها و تناقض‌ها\n\n' + result + '\n\n⚖️ موارد گزارش‌شده سرنخ بررسی هستند، نه اثبات قطعی نادرستی یکی از اسناد.'


def review_contract_risks(extracted_text, contract_type='نامشخص', playbook=None, *, preference_uid=None):
    """Produce conservative, source-quoted contract review candidates.

    This is an AI-menu service helper, not a legal opinion. Findings are retained
    only when the quoted clause is present in the supplied extracted text.
    """
    if not (AI_ENABLED and DEEPSEEK_API_KEY and AI_EXTERNAL_DATA_CONSENT):
        raise RuntimeError('AI disabled, key missing, or external-data consent not enabled')
    text = str(extracted_text or '').strip()
    if not text:
        raise ValueError('متن استخراج‌شده قرارداد برای بررسی وجود ندارد')

    max_input = min(9000, max(1500, AI_TEXT_MAX_CHARS - 1400))
    truncated = len(text) > max_input
    if truncated:
        head = int(max_input * 0.6)
        tail = max_input - head
        text_for_review = text[:head] + '\n\n[بخش‌هایی از متن قرارداد برای کنترل هزینه ارسال نشده‌اند]\n\n' + text[-tail:]
    else:
        text_for_review = text

    playbook_criteria = []
    if isinstance(playbook, dict):
        playbook_criteria = [str(item.get('label') or '').strip() for item in playbook.get('criteria', []) if isinstance(item, dict) and str(item.get('label') or '').strip()]
    criteria_text = '\n'.join(f'- {label}' for label in playbook_criteria[:20]) or '- بررسی عمومی بندهای مرتبط قرارداد'
    playbook_title = str((playbook or {}).get('title') or contract_type or 'نامشخص')[:120]
    criterion_ids = [str(item.get('id') or '').strip() for item in (playbook or {}).get('criteria', []) if isinstance(item, dict) and str(item.get('id') or '').strip()] if isinstance(playbook, dict) else []
    criterion_id_text = ', '.join(criterion_ids[:20]) or 'general'
    prompt = f'''قرارداد را فقط به‌عنوان بررسی اولیه و محافظه‌کارانه تحلیل کن.
نوع قرارداد / الگوی بررسی: {playbook_title}
معیارهای الگوی انتخاب‌شده (در صورت ارتباط با متن بررسی کن؛ نبودن بند را قطعی فرض نکن):
{criteria_text}

فقط JSON معتبر با این ساختار برگردان:
{{"findings":[{{"criterion_id":"شناسه یکی از معیارهای مجاز: {criterion_id_text}","topic":"موضوع بند","risk":"زیاد یا متوسط یا کم یا نامشخص","quote":"نقل‌قول عین متن قرارداد","reason":"چرا این بند ممکن است مبهم، نامتوازن یا نیازمند بررسی باشد","suggestion":"پیشنهاد بررسی یا اصلاح، بدون افزودن واقعیت جدید"}}]}}

قواعد:
- حداکثر ۸ یافته؛ فقط یافته‌های مشخص و مربوط به متن را ارائه کن.
- quote باید عیناً از متن زیر انتخاب شود؛ نقل‌قول نساز و بازنویسی نکن.
- مواردی مانند طرفین و سمت‌ها، موضوع، مبلغ/نحوه پرداخت، مهلت‌ها، تحویل، تضمین، مسئولیت، فسخ/خاتمه، حل اختلاف و بندهای متعارض را فقط اگر در متن مربوط باشند بررسی کن.
- نبود یک بند در متن استخراج‌شده را با قطعیت به معنی نبود آن در قرارداد کامل ندان.
- ریسک حقوقی قطعی، اعتبار یا بطلان قرارداد و نتیجه دعوا را اعلام نکن؛ برای موارد وابسته به قانون یا شرایط بیرونی، صریحاً بررسی حقوقی لازم را بگو.
- هیچ ماده قانونی، رأی، مهلت قانونی یا واقعیت جدیدی اختراع نکن.
- پیشنهاد اصلاحی باید به‌عنوان گزینه‌ای برای بررسی مطرح شود، نه متن قطعی و آماده امضا.
- اگر شاهد متنی مشخصی برای یافته نداری، آن را گزارش نکن.

متن استخراج‌شده قرارداد:
{text_for_review}'''
    raw_result = _call_feature([
        {'role': 'system', 'content': 'بررسی‌گر اولیه قرارداد، محتاط و وفادار به شواهد. فقط JSON معتبر؛ هیچ قانون یا واقعیتی جعل نکن.'},
        {'role': 'user', 'content': prompt},
    ], temperature=0.0, feature='contract_review', preference_uid=preference_uid)
    try:
        payload = _json(str(raw_result or ''))
    except (ValueError, TypeError, json.JSONDecodeError):
        payload = {}

    source = _normalize_evidence_quote(text_for_review)
    findings = []
    allowed_risks = {'زیاد', 'متوسط', 'کم', 'نامشخص'}
    items = payload.get('findings', []) if isinstance(payload, dict) else []
    if isinstance(items, list):
        for item in items[:8]:
            if not isinstance(item, dict):
                continue
            quote = str(item.get('quote') or '').strip()
            normalized_quote = _normalize_evidence_quote(quote)
            if len(normalized_quote) < 12 or normalized_quote not in source:
                continue
            risk = str(item.get('risk') or 'نامشخص').strip()
            if risk not in allowed_risks:
                risk = 'نامشخص'
            topic = re.sub(r'\s+', ' ', str(item.get('topic') or 'بند نیازمند بررسی')).strip()[:140]
            reason = re.sub(r'\s+', ' ', str(item.get('reason') or 'دلیل کافی ارائه نشده است.')).strip()[:500]
            suggestion = re.sub(r'\s+', ' ', str(item.get('suggestion') or 'بند با متن کامل قرارداد و شرایط معامله تطبیق داده شود.')).strip()[:500]
            criterion_id = str(item.get('criterion_id') or '').strip()
            if criterion_id not in criterion_ids:
                criterion_id = ''
            findings.append({'criterion_id': criterion_id, 'topic': topic, 'risk': risk, 'quote': quote[:600], 'reason': reason, 'suggestion': suggestion})

    if criterion_ids:
        labels = {str(item.get('id')): str(item.get('label') or item.get('id')) for item in playbook.get('criteria', []) if isinstance(item, dict)}
        matched_ids = {item['criterion_id'] for item in findings if item['criterion_id']}
        uncovered = [labels.get(cid, cid) for cid in criterion_ids if cid not in matched_ids]
        high_count = sum(item['risk'] == 'زیاد' for item in findings)
        medium_count = sum(item['risk'] == 'متوسط' for item in findings)
        low_count = sum(item['risk'] == 'کم' for item in findings)
        lines = [
            '📌 خلاصه مدیریتی بررسی',
            f"• معیارهای دارای یافته مستند: {len(matched_ids)} از {len(criterion_ids)}",
            f"• یافته‌های قابل استناد به متن: {len(findings)} (زیاد: {high_count}، متوسط: {medium_count}، کم: {low_count})",
            f"• معیارهای بدون شاهد کافی در متن بررسی‌شده: {len(uncovered)}",
        ]
        if uncovered:
            lines.append('• مواردی که اطلاعات/مدرک تکمیلی درباره آن‌ها مفید است: ' + '؛ '.join(uncovered[:8]))
        questions = (playbook or {}).get('follow_up_questions', []) if isinstance(playbook, dict) else []
        if questions:
            lines.append('• پرسش‌های تکمیلی پیشنهادی:')
            lines.extend(f'  - {str(question)[:300]}' for question in questions[:5])
        lines.extend([
            '⚠️ این خلاصه فقط یافته‌های متکی به نقل‌قول و معیارهای بررسی‌شده را جمع‌بندی می‌کند؛ نبود یافته، اثبات رعایت معیار یا بی‌اشکال بودن قرارداد نیست.',
            '',
            '🧾 گزارش معیاربه‌معیار Playbook — بررسی اولیه و نیازمند بازبینی'
        ])
        for criterion_id in criterion_ids:
            matched = [item for item in findings if item['criterion_id'] == criterion_id]
            lines.append(f"\n• {labels.get(criterion_id, criterion_id)} — {'دارای یافته' if matched else 'نیازمند بررسی / شاهد کافی در متن بررسی‌شده یافت نشد'}")
            for item in matched:
                lines.append(f"  شاهد: «{item['quote']}»\n  دلیل: {item['reason']}\n  ریسک پیشنهادی: {item['risk']}\n  پیشنهاد: {item['suggestion']}")
        unmatched = [item for item in findings if not item['criterion_id']]
        for item in unmatched:
            lines.append(f"\n• یافته مرتبطِ بدون تطبیق قطعی با معیار: {item['topic']}\n  شاهد: «{item['quote']}»\n  دلیل: {item['reason']}\n  پیشنهاد: {item['suggestion']}")
        result = '\n'.join(lines)
    elif findings:
        lines = ['🧾 بررسی اولیه قرارداد — یافته‌ها نیازمند بازبینی هستند']
        for index, item in enumerate(findings, 1):
            lines.append(f"\n{index}. {item['topic']} | سطح پیشنهادی ریسک: {item['risk']}\n   شاهد از متن: «{item['quote']}»\n   دلیل بررسی: {item['reason']}\n   پیشنهاد: {item['suggestion']}")
        result = '\n'.join(lines)
    else:
        result = 'از پاسخ مدل، یافته‌ای با نقل‌قول قابل تطبیق با متن ورودی به دست نیامد. این نتیجه به معنی بی‌اشکال بودن قرارداد نیست.'
    if truncated:
        result += '\n\n⚠️ محدودیت پوشش: فقط بخش‌هایی از متن استخراج‌شده بررسی شده‌اند؛ این گزارش، بررسی کامل قرارداد نیست.'
    result += '\n\n⚖️ این گزارش بررسی اولیه است، نه نظر حقوقی قطعی. متن کامل قرارداد، پیوست‌ها، شرایط معامله و قانون قابل اعمال باید جداگانه بررسی شوند.'
    return result
