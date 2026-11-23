import re
MAX_TELEGRAM_MESSAGE=4000
from .text_guard import sanitize_result, normalize_output

def _pages(items):
    p=[]
    for x in items or []:
        if isinstance(x,dict):
            ps=x.get('source_pages') or x.get('pages') or []
            if ps: p.extend(ps)
    return sorted(set(p))

def analysis_text(r):
    r=sanitize_result(r)
    s=['📁 بررسی اولیه پرونده','']
    s.append('🧩 متن با موتور داخلی خلاصه شده نه با AI')
    ex=r.get('extraction') or {}
    if ex:
        o=ex.get('ocr') or {}
        state=ex.get('status','—')
        quality=ex.get('quality',0)
        s += ['', '🔧 وضعیت استخراج سند']
        s.append(f'• وضعیت: {state} | کیفیت متن: {quality:.0%} | تعداد صفحات: {ex.get("pages",0)}')
        s.append(f'• متن: {ex.get("text_chars",0):,} نویسه | استخراج عادی: {ex.get("native_pages",0)} صفحه | OCR: {ex.get("ocr_pages",0)} صفحه')
        if ex.get('native_fallback_pages'): s.append(f'• ⚠️ {ex["native_fallback_pages"]} صفحه مشکوک بود و چون OCR در دسترس/موفق نبود، متن عادی به‌عنوان پشتیبان استفاده شد.')
        if o.get('found') is False:
            s.append('• ❌ Tesseract/Persian OCR آماده نیست؛ برای PDF اسکن‌شده باید این مورد اصلاح شود.')
            if o.get('missing_languages'): s.append('• زبان‌های مفقود: '+', '.join(o['missing_languages']))
        elif o.get('found') is True:
            s.append('• ✅ Tesseract و زبان‌های درخواستی OCR در دسترس هستند.')
        if o.get('error'): s.append('• ⚠️ '+str(o['error']))
    if r.get('document_type'): s += ['',f'📄 نوع سند: {r["document_type"]}']
    overview = r.get('overview') or []
    if overview:
        s += ['', '🧭 نمای کلی پرونده']
        for line in overview[:8]:
            if line:
                s.append(f'• {line}')
    stats = r.get('stats') or {}
    if stats:
        s += ['', '📊 پوشش استخراج',
              f"طرفین {stats.get('parties',0)} | تاریخ {stats.get('dates',0)} | مبلغ {stats.get('amounts',0)} | "
              f"خواسته {stats.get('claims',0)} | تعهد {stats.get('obligations',0)} | ماده {stats.get('refs',0)} | بند متنی {stats.get('snippets',0)}"]

    # Important numeric facts are shown verbatim from extraction and isolated
    # on their own lines. This prevents Persian RTL text from visually changing
    # the order of digits/separators and makes accidental transcription changes
    # immediately visible to the lawyer.
    numeric_blocks=[]
    seen_numeric=set()
    for key, label in [('amounts','💰 مبلغ'), ('dates','📅 تاریخ')]:
        for x in (r.get(key) or [])[:20]:
            if isinstance(x, dict):
                v=str(x.get('value') or '').strip()
            else:
                v=str(x or '').strip()
            if v and v not in seen_numeric:
                seen_numeric.add(v)
                numeric_blocks.append((label, v))
    if numeric_blocks:
        s += ['', '🔢 اعداد و تاریخ‌های مهم — عیناً از متن سند']
        for label, value in numeric_blocks:
            s += ['', f'{label}:', value, '']
    for title,key,field in [('👥 طرفین','parties','name'),('🎯 خواسته‌ها/ادعاها','claims','claim'),('🕐 تاریخ‌های مهم','dates','value'),('💰 مبالغ','amounts','value'),('📌 تعهدات','obligations','text'),('⚖️ مراجع قانونی ذکرشده','legal_references','reference'),('🏛 مرجع/کلاسه/شعبه','courts','value'),('🔍 اشارات دلیلی','evidence','text'),('📌 خواسته/اثر اجرایی','remedies','text'),('⚠️ شروط حساس','sensitive_clauses','text')]:
        vals=r.get(key) or []
        if not vals: continue
        s += ['',title]
        for x in vals[:16]:
            text=(x.get(field) if isinstance(x,dict) else str(x)) or ''
            pages=(x.get('source_pages') or []) if isinstance(x,dict) else []
            role=x.get('role') if isinstance(x,dict) else None
            if role and field=='name': text=f'{text} ({role})'
            s.append('• '+str(text)+(f' — صفحه {", ".join(map(str,pages))}' if pages else ''))
    ci=r.get('case_intelligence') or {}
    if ci:
        s += ['', '🧠 هوش پرونده — تحلیل ساختاریافته']
        if ci.get('document_type'): s.append('• نوع سند احتمالی: '+str(ci['document_type']))
        if ci.get('issues'):
            s += ['', '🎯 مسائل/محورهای شناسایی‌شده']
            for item in ci['issues'][:10]:
                sig=item.get('signals') or []
                pages=sorted({p for x in sig for p in (x.get('source_pages') or [])})
                s.append('• '+item.get('issue','')+(f' — صفحه {", ".join(map(str,pages))}' if pages else ''))
        if ci.get('missing_items'):
            s += ['', '📎 مواردی که در متن استخراج‌شده پیدا نشدند']
            for item in ci['missing_items'][:10]: s.append('• '+item.get('message',''))
        if ci.get('evidence_matrix'):
            s += ['', '🔗 تطبیق اولیه ادعا و دلیل']
            for item in ci['evidence_matrix'][:10]:
                st='دارای نشانه مرتبط' if item.get('evidence') else 'نشانه مرتبط پیدا نشد'
                s.append('• '+item.get('claim','')[:300]+' — '+st)
                for ev in (item.get('evidence') or [])[:1]:
                    pg=ev.get('source_pages') or []
                    s.append('  ↳ '+ev.get('text','')[:320]+(f' — صفحه {", ".join(map(str,pg))}' if pg else ''))
        if ci.get('intelligence_flags'):
            s += ['', '⚠️ پرچم‌های بازبینی']
            for x in ci['intelligence_flags'][:8]: s.append('• '+x.get('message',''))
        if ci.get('confidence_note'): s += ['', '🛡 '+ci['confidence_note']]
    important=r.get('important_terms') or []
    if important:
        s += ['', '🔎 کلمات و عبارات مهم شناسایی‌شده']
        s.append('• این موارد فقط نشانه‌های متنی هستند و به‌تنهایی نتیجه حقوقی محسوب نمی‌شوند.')
        shown=[]
        for x in important[:30]:
            phrase=(x.get('phrase') if isinstance(x,dict) else str(x)).strip()
            if phrase and phrase not in shown:
                shown.append(phrase)
        if shown: s.append('• '+'، '.join(shown))
    sensitive=r.get('sensitive_clauses') or []
    if sensitive:
        s += ['', '🚨 شروط و عبارات حساس']
        for x in sensitive[:15]:
            text=x.get('text','') if isinstance(x,dict) else str(x)
            pages=x.get('source_pages',[]) if isinstance(x,dict) else []
            s.append('🔴 '+text+(f' — صفحه {", ".join(map(str,pages))}' if pages else ''))
    timeline=r.get('timeline') or []
    if timeline:
        s += ['', '🗓 خط زمانی اولیه']
        for x in timeline[:18]: s.append(f'• {x.get("date","")} — {x.get("event","")}'+(f' — صفحه {", ".join(map(str,x.get("source_pages",[])))}' if x.get('source_pages') else ''))
    contr=r.get('contradictions') or []
    if contr:
        s += ['', '⚠️ مواردی که نیاز به تطبیق دارند']
        for x in contr[:12]: s.append('• '+x.get('message','')+(f' ({"، ".join(map(str,x.get("values",[])))})' if x.get('values') else ''))
    s += ['', '📝 خلاصه کامل‌تر و محافظه‌کارانه پرونده']
    s.append('• این بخش برای دیدن تصویر کلی پرونده است؛ جمله‌ها از متن خود پرونده انتخاب شده‌اند تا تاریخ، مبلغ، نام و ادعاها بدون حدس‌زدن حفظ شوند.')
    for x in (r.get('summary') or [])[:24]:
        s.append('• '+x.get('text','')+(f' — صفحه {", ".join(map(str,x.get("source_pages",[]))) or x.get("page","")}' if (x.get('source_pages') or x.get('page')) else ''))
    risks=r.get('risks') or []
    if risks:
        s += ['', '⚠️ ریسک‌ها/بندهای قابل توجه']
        for x in risks[:18]:
            details=[]
            for h in x.get('hits',[]): details.append(h.get('term','')+(f' صفحه {",".join(map(str,h.get("pages",[])))}' if h.get('pages') else ''))
            s.append(f'{x.get("icon","🟡")} {x.get("title","")}'+(f' — {"؛ ".join(details)}' if details else ''))
    else: s.append('• مورد مشخصی از قواعد فعال پیدا نشد؛ این به معنی نبود ریسک نیست.')
    warnings=r.get('output_warnings') or []
    if warnings:
        s += ['', '🛡 بررسی کیفیت خروجی']
        for w in warnings: s.append('• '+w)
    s += ['', '💡 برای بررسی یک عبارت داخل همین پرونده، از «جستجو در پرونده» استفاده کنید.']
    s += ['📍 شماره صفحات به اصل سند ارجاع می‌دهند.','⚠️ این بررسی خودکار است و جایگزین بررسی و نظر وکیل نیست.']
    return normalize_output('\n'.join(s))


def _fa_digits(value):
    return str(value).translate(str.maketrans('0123456789','۰۱۲۳۴۵۶۷۸۹'))


def _page_tag(item):
    if not isinstance(item,dict):
        return ''
    pages=item.get('source_pages') or []
    pages=sorted({int(x) for x in pages if isinstance(x,(int,str)) and str(x).isdigit()})
    return f" [ص {_fa_digits('، '.join(map(str,pages)))}]" if pages else ''


def _clean_unique_text(items, keys=('text','claim','fact','event'), limit=8):
    out=[]; seen=set()
    for item in items or []:
        if isinstance(item,dict):
            value=''
            for key in keys:
                if item.get(key):
                    value=str(item.get(key)).strip(); break
        else:
            value=str(item or '').strip()
        value=re.sub(r'\s+',' ',value).strip()
        if len(value)<8: continue
        marker=value
        if marker in seen: continue
        seen.add(marker); out.append((value,item))
        if len(out)>=limit: break
    return out


def case_summary_text(r):
    """Compact, lawyer-readable, source-backed case summary.

    This is intentionally separate from ``analysis_text``.  The latter is a
    broad diagnostic report; the case-summary button should not dump every
    extractor signal into one Telegram message.
    """
    r=sanitize_result(r or {})
    lines=['🧾 خلاصه‌گر پرونده','',
           'خلاصه استخراجی از متن پرونده است؛ بازنویسی آزاد یا نتیجه‌گیری حقوقی انجام نشده.']

    if r.get('document_type'):
        lines += ['', f"📄 نوع سند: {r['document_type']}"]

    parties=[]; seen=set()
    for x in r.get('parties') or []:
        if not isinstance(x,dict): continue
        name=str(x.get('name') or '').strip(); role=str(x.get('role') or '').strip()
        if not name or len(name)>80: continue
        key=(name,role)
        if key in seen: continue
        seen.add(key); parties.append(x)
    if parties:
        lines += ['', '👥 طرفین']
        for x in parties[:8]:
            role=str(x.get('role') or 'طرف').strip()
            name=str(x.get('name') or '').strip()
            lines.append(f'• {role}: {name}{_page_tag(x)}')

    claims=[]; seen=set()
    for x in r.get('claims') or []:
        if not isinstance(x,dict): continue
        text=str(x.get('claim') or '').strip()
        ctype=str(x.get('claim_type') or '').strip()
        # Generic contract statements are not useful as «خواسته» unless they
        # actually look like a request/defense.
        if ctype not in ('درخواست/مطالبه','دفاع/اعتراض') and not re.search(r'درخواست|تقاضا|مطالبه|محکومیت|الزام|اعتراض|دفاع',text):
            continue
        key=text
        if not text or key in seen: continue
        seen.add(key); claims.append(x)
    if claims:
        lines += ['', '🎯 خواسته‌ها و مواضع صریح']
        for x in claims[:6]:
            label='دفاع/اعتراض' if x.get('claim_type')=='دفاع/اعتراض' else 'درخواست/مطالبه'
            lines.append(f"• {label}: {x.get('claim','').strip()}{_page_tag(x)}")

    amounts=[]; seen=set()
    for x in r.get('amounts') or []:
        if not isinstance(x,dict): continue
        v=str(x.get('value') or '').strip()
        if not v or v in seen: continue
        seen.add(v); amounts.append(x)
    if amounts:
        lines += ['', '💰 مبالغ مهم']
        for x in amounts[:8]: lines.append(f"• {x.get('value','').strip()}{_page_tag(x)}")

    dates=[]; seen=set()
    for x in r.get('dates') or []:
        if not isinstance(x,dict): continue
        v=str(x.get('value') or '').strip()
        if not v or v in seen: continue
        seen.add(v); dates.append(x)
    if dates:
        lines += ['', '📅 تاریخ‌های مهم']
        for x in dates[:10]: lines.append(f"• {x.get('value','').strip()}{_page_tag(x)}")

    obligations=_clean_unique_text(r.get('obligations'),keys=('text',),limit=6)
    if obligations:
        lines += ['', '📌 تعهدات/الزامات صریح']
        for text,x in obligations: lines.append(f'• {text}{_page_tag(x)}')

    sensitive=[]; seen=set()
    for x in r.get('sensitive_clauses') or []:
        if not isinstance(x,dict): continue
        text=str(x.get('text') or '').strip()
        if not text or text in seen: continue
        seen.add(text); sensitive.append(x)
    if sensitive:
        lines += ['', '⚠️ بندها و موضوعات حساسِ دیده‌شده']
        for x in sensitive[:8]:
            lines.append(f"• {x.get('label','موضوع حساس')}: {x.get('text','').strip()}{_page_tag(x)}")

    narrative=[]; seen=set()
    # Prefer the ranked source snippets but do not repeat structured facts.
    structured={re.sub(r'\s+',' ',str(x.get('claim') or x.get('text') or '').strip()) for x in (r.get('claims') or []) if isinstance(x,dict)}
    structured |= {re.sub(r'\s+',' ',str(x.get('text') or '').strip()) for x in (r.get('obligations') or []) if isinstance(x,dict)}
    structured |= {re.sub(r'\s+',' ',str(x.get('text') or '').strip()) for x in (r.get('sensitive_clauses') or []) if isinstance(x,dict)}
    amounts_values=[str(x.get('value') or '').strip() for x in (r.get('amounts') or []) if isinstance(x,dict)]
    for x in r.get('summary') or []:
        if not isinstance(x,dict): continue
        text=re.sub(r'\s+',' ',str(x.get('text') or '').strip())
        # A pure numeric/financial sentence is already represented above; do
        # not repeat it in the narrative section. Keep sentences that combine
        # an amount with an actual event such as payment or default.
        pure_amount=any(v and v in text for v in amounts_values) and not re.search(r'پرداخت|تسویه|مطالبه|تعیین|تأخیر|عدم\s+پرداخت|مبلغ.*(?:است|بود)',text)
        if len(text)<25 or text in seen or text in structured or pure_amount: continue
        seen.add(text); narrative.append(x)
        if len(narrative)>=8: break
    if narrative:
        lines += ['', '📝 روایت کوتاه از متن پرونده']
        for x in narrative: lines.append(f"• {x.get('text','').strip()}{_page_tag(x)}")

    checks=[]
    for x in r.get('contradictions') or []:
        if isinstance(x,dict) and x.get('message'): checks.append(str(x['message']).strip())
    ci=r.get('case_intelligence') or {}
    for x in ci.get('missing_items') or []:
        if isinstance(x,dict) and x.get('message'): checks.append(str(x['message']).strip())
    checks=list(dict.fromkeys(checks))
    if checks:
        lines += ['', '🔎 موارد نیازمند تطبیق']
        for x in checks[:6]: lines.append('• '+x)

    if not parties and not claims and not amounts and not dates and not narrative:
        lines += ['', 'ℹ️ از متن استخراج‌شده اطلاعات ساختاری کافی برای خلاصه‌سازی پیدا نشد.']

    lines += ['', '📍 ارجاع‌های «ص N» به شماره صفحه اصل سند اشاره دارند.',
              '⚠️ این خلاصه خودکار است و برای استفاده حقوقی باید با اصل اسناد کنترل شود.']
    return normalize_output('\n'.join(lines))

def _result_kind_label(r):
    """Human-readable badge so Telegram users know what type of hit they see."""
    kind = (r.get('kind') or 'law').strip()
    law_title = str(r.get('law') or '')
    if kind == 'ruling':
        return '⚖️ رأی وحدت رویه'
    if kind == 'consultation':
        return '💬 نظریه مشورتی'
    if kind == 'sample':
        return '📝 نمونه آموزشی'
    if kind == 'circular':
        return '📢 بخشنامه / ضابطه'
    if law_title.startswith('نمونه:') or 'نمونه:' in law_title[:12]:
        return '📝 نمونه آموزشی'
    if law_title.startswith('بخشنامه:') or 'بخشنامه:' in law_title[:15]:
        return '📢 بخشنامه / ضابطه'
    if law_title.startswith('بسته ') or law_title.startswith('بسته عملی') or law_title.startswith('بسته کاربردی'):
        return '📦 بسته کاربردی (راهنما)'
    if 'آیین' in law_title[:20] or law_title.startswith('آیین‌نامه'):
        return '📋 آیین‌نامه'
    return '📜 قانون / ماده'


def law_text(results):
    if not results:
        return (
            '❌ نتیجه‌ای پیدا نشد.\n\n'
            'چند پیشنهاد برای جستجوی بهتر:\n'
            '• نام قانون + ماده (مثال: قانون مدنی ماده ۱۰۸۲)\n'
            '• موضوع روزمره (مثال: سقف اجاره / مهریه / کمیسیون ماده ۱۰۰)\n'
            '• نمونه یا بخشنامه (مثال: نمونه دادخواست مهریه / بخشنامه ثنا)\n\n'
            'از منو می‌توانید دوباره «🔎 جستجو در منابع حقوقی» را بزنید.'
        )
    s = [
        '📚 نتایج جستجو در منابع حقوقی',
        '',
        'راهنمای برچسب‌ها:',
        '📜 قانون/ماده · 📦 بسته کاربردی · 📝 نمونه · 📢 بخشنامه · ⚖️ رأی · 💬 نظریه',
        '',
    ]
    partial = False
    for i, r in enumerate(results, 1):
        from .laws import clean_legal_text
        text = clean_legal_text(r.get('clean_text') or r.get('text', ''))
        badge = _result_kind_label(r)
        kind = (r.get('kind') or 'law').strip()
        if kind == 'ruling':
            status = r.get('verification_label') or 'وضعیت نامشخص'
            s += [
                f'{badge} — {i}) {r.get("title", "رأی وحدت رویه")}',
                f'📅 تاریخ: {r.get("date", "—")} | وضعیت متن: {status}',
                text[:1100],
                '',
            ]
            if 'ناقص' in status or 'خلاصه' in status:
                partial = True
        elif kind == 'consultation':
            status = r.get('verification_label') or 'وضعیت نامشخص'
            s += [
                f'{badge} — {i}) {r.get("title", "نظریه مشورتی")}',
                f'📅 تاریخ: {r.get("date", "—")} | وضعیت متن: {status}',
                f'❓ سؤال: {r.get("question", "")[:650]}',
                f'💡 نظریه: {text[:1100]}',
                '',
            ]
        elif kind in ('sample', 'circular'):
            title = r.get('title') or r.get('law') or 'مورد'
            extra = []
            if r.get('category'):
                extra.append(f'دسته: {r["category"]}')
            if r.get('court'):
                extra.append(f'مرجع معمول: {r["court"]}')
            if r.get('claim'):
                extra.append(f'خواسته: {str(r["claim"])[:200]}')
            if r.get('reference'):
                extra.append(f'مرجع: {r["reference"]}')
            s.append(f'{badge} — {i}) {title}')
            if extra:
                s.append(' · '.join(extra))
            s += [text[:1100], '']
        else:
            art = r.get('article') or '—'
            s += [
                f'{badge} — {i}) {r.get("law", "—")}',
                f'ماده / بند: {art}',
                text[:1100],
            ]
        # V131: every research hit carries an explicit citation envelope.
        # Show provenance separately from the legal text so the user can
        # distinguish source metadata from the retrieved content.
        citation = r.get('citation') or {}
        if citation:
            status = citation.get('verification_label') or 'وضعیت منبع نامشخص'
            authorities = '، '.join(citation.get('primary_sources') or [])
            verified = citation.get('last_verified')
            urls = citation.get('source_urls') or []
            s.append(f'🧾 استناد: {citation.get("id","—")}')
            s.append(f'🛡 اعتبار: {status}')
            if authorities:
                s.append('🏛 مرجع منبع: '+authorities)
            if verified:
                s.append('📅 آخرین تطبیق ثبت‌شده: '+str(verified))
            if citation.get('source_file'):
                s.append('📄 فایل/نسخه منبع: '+str(citation['source_file']))
            if urls:
                s.append('🔗 منبع رسمی: '+str(urls[0]))
            if citation.get('activation_note'):
                s.append('ℹ️ '+str(citation['activation_note']))
        s.append('')
    if partial:
        s += [
            '⚠️ بعضی آراء به‌صورت ناقص/خلاصه در منبع ورودی بودند؛ برای استناد نهایی با منبع رسمی تطبیق دهید.',
            '',
        ]
    s += [
        'ℹ️ برچسب «بسته کاربردی» و «نمونه» راهنمای عملی‌اند، نه متن جایگزین قانون.',
        'وضعیت اعتبار هر مورد را با منبع رسمی کنترل کنید. «استناد» در هر نتیجه شناسه و اطلاعات provenance همان رکورد را نشان می‌دهد؛ نبود لینک به معنی وجود منبع رسمی تأییدشده نیست.',
    ]
    return '\n'.join(s)


async def reply_long(message,text):
    # Apply the same final RTL/LTR numeric protection to every outgoing path,
    # including law search results and future message types.
    text=normalize_output(text or '—')
    while len(text)>MAX_TELEGRAM_MESSAGE:
        cut=text.rfind('\n',0,MAX_TELEGRAM_MESSAGE)
        if cut<1000: cut=text.rfind(' ',0,MAX_TELEGRAM_MESSAGE)
        if cut<1000: cut=MAX_TELEGRAM_MESSAGE
        await message.reply_text(text[:cut].rstrip())
        text=text[cut:].lstrip()
    if text: await message.reply_text(text)
