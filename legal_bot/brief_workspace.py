"""Lightweight local-first workspace helpers for legal briefs.

Keeps the Telegram UX simple while adding editing, review, versioning and
export support. No external AI is required.
"""
from __future__ import annotations
import re
from datetime import datetime
from typing import List, Tuple


def remember_version(state: dict, text: str, label: str = 'پیش‌نویس') -> int:
    text = str(text or '').strip()
    if not text:
        return 0
    versions = state.setdefault('brief_versions', [])
    if versions and versions[-1].get('text') == text:
        return int(versions[-1].get('version', len(versions)))
    n = int(versions[-1].get('version', 0)) + 1 if versions else 1
    versions.append({'version': n, 'label': label, 'text': text,
                     'created_at': datetime.now().isoformat(timespec='seconds')})
    state['brief_current_text'] = text
    # Keep Telegram state bounded.
    if len(versions) > 12:
        del versions[:-12]
    return n


def current_text(state: dict) -> str:
    return str(state.get('brief_current_text') or '').strip()


def history_lines(state: dict) -> List[str]:
    out = []
    for v in reversed(state.get('brief_versions') or []):
        out.append(f"V{v['version']} — {v.get('label','نسخه')} — {v.get('created_at','')}")
    return out


def get_version(state: dict, number: int):
    for v in state.get('brief_versions') or []:
        if int(v.get('version', -1)) == int(number):
            return v
    return None


def _replace_section(text: str, section: str, replacement: str) -> str:
    # Matches Persian/Arabic or Latin numbered headings such as "3) دفاعیات"
    pat = re.compile(rf'(?ms)^\s*(\d+\)\s*[^\n]*{re.escape(section)}[^\n]*)\n.*?(?=^\s*\d+\)\s|^\s*─{{8,}}|\Z)')
    m = pat.search(text)
    if not m:
        return text
    heading = m.group(1)
    return text[:m.start()] + heading + '\n' + replacement.strip() + '\n\n' + text[m.end():]


def apply_local_edit(text: str, instruction: str) -> Tuple[str, str]:
    """Apply safe, explicit edits without pretending to do legal reasoning.

    Supported examples:
      - «شرح ماوقع: ...» / «دفاعیات: ...» / «خواسته: ...»
      - «بخش ... را حذف کن»
      - «متن را کوتاه کن» (removes redundant review/meta tail only)
      - «هشدارها را حذف کن»
    Other instructions are returned as a note rather than silently inventing text.
    """
    text = text.strip(); ins = str(instruction or '').strip()
    if not text or not ins:
        return text, 'دستور و متن لایحه کافی نیست.'

    # Explicit section replacement: user supplies the new text.
    m = re.match(r'^\s*(?:بخش\s+)?(شرح ماوقع|شرح مختصر موضوع و وقایع|دفاعیات|مستندات|خواسته|تقاضای پایانی|پیوست‌ها)\s*[:：]\s*(.+)$', ins, re.S)
    if m:
        section, repl = m.group(1), m.group(2).strip()
        new = _replace_section(text, section, repl)
        if new != text:
            return new, f'بخش «{section}» با متن ارسالی شما جایگزین شد.'
        return text, f'بخش «{section}» در متن پیدا نشد؛ متن اصلی دست‌نخورده ماند.'

    # Safe deletion of a named section.
    m = re.match(r'^\s*بخش\s+(شرح ماوقع|شرح مختصر موضوع و وقایع|دفاعیات|مستندات|خواسته|تقاضای پایانی|پیوست‌ها)\s+را\s+(?:حذف|بردار)', ins)
    if m:
        section = m.group(1)
        pat = re.compile(rf'(?ms)^\s*\d+\)\s*[^\n]*{re.escape(section)}[^\n]*\n.*?(?=^\s*\d+\)\s|^\s*─{{8,}}|\Z)')
        new, n = pat.subn('', text, count=1)
        return new.strip(), (f'بخش «{section}» حذف شد.' if n else f'بخش «{section}» پیدا نشد.')

    low = ins.replace('‌',' ')
    if 'کوتاه' in low and ('متن' in low or 'لایحه' in low):
        # Remove only machine-generated meta/review material; never invent or
        # rewrite factual/legal content.
        new = re.split(r'\n\s*🔎 گزارش بررسی\s*\n', text, maxsplit=1)[0]
        new = re.split(r'\n\s*⚠️ این خروجی پیش‌نویس داخلی', new, maxsplit=1)[0].rstrip()
        return new, 'بخش‌های توضیحی/کنترلی حذف شد؛ محتوای اصلی دست‌نخورده ماند.'
    if 'هشدار' in low and 'حذف' in low:
        lines = [x for x in text.splitlines() if not x.strip().startswith('⚠️')]
        return '\n'.join(lines).strip(), 'هشدارهای نمایشی حذف شدند.'

    return text, 'این دستور به‌صورت محلی قابل اجرای ایمن نیست؛ متن اصلی دست‌نخورده ماند. برای تغییر یک بخش، نام بخش و متن جدید را به شکل «دفاعیات: ...» ارسال کنید.'


def diff_summary(old: str, new: str) -> str:
    import difflib
    old_lines = old.splitlines(); new_lines = new.splitlines()
    added = sum(1 for x in difflib.ndiff(old_lines, new_lines) if x.startswith('+ '))
    removed = sum(1 for x in difflib.ndiff(old_lines, new_lines) if x.startswith('- '))
    return f'افزوده‌شده: {added} خط | حذف‌شده: {removed} خط'


def compare_versions(state: dict, older: int, newer: int | None = None) -> str:
    """Return a compact, human-readable diff between two saved brief versions."""
    import difflib
    a = get_version(state, older)
    b = get_version(state, newer) if newer is not None else None
    if b is None:
        b_text = current_text(state)
        b_no = 'نسخه فعال'
    else:
        b_text = b.get('text','')
        b_no = f"V{b.get('version')}"
    if not a:
        return 'نسخه مبنا پیدا نشد.'
    diff = list(difflib.unified_diff(
        a.get('text','').splitlines(), b_text.splitlines(),
        fromfile=f"V{a.get('version')}", tofile=b_no, lineterm=''
    ))
    if not diff:
        return f"V{a.get('version')} و {b_no} تفاوت متنی ندارند."
    # Keep Telegram output bounded and useful: omit unified header noise.
    body = [x for x in diff if not x.startswith(('---','+++','@@'))]
    return '\n'.join(body[:180])

def add_inline_citations(text: str, sources=None) -> str:
    """Add citations only where an explicit source locator already appears in text."""
    # Rebuild citation markers from the current source pack so deleting/reordering
    # sources cannot leave stale [C#] markers pointing at a different source.
    out = re.sub(r'\s*\[C\d+\]', '', text or '')
    for i, src in enumerate(sources or [], 1):
        c = src.get('citation') if isinstance(src, dict) else {}
        cid = str((c or {}).get('id') or '').strip()
        if not cid:
            continue
        article = str(src.get('article') or src.get('ماده') or '').strip()
        ruling = str(src.get('ruling_number') or '').strip()
        title = str(src.get('title') or src.get('law') or src.get('name') or '').strip()
        markers=[]
        if article:
            markers += [f'ماده {article}', f'مواد {article}']
        if ruling:
            markers += [f'رأی وحدت رویه {ruling}', f'رأی شماره {ruling}']
        # Do not create a citation merely from a source title; a locator must
        # already be present in the draft.
        for marker in markers:
            if marker in out and f'{marker} [C{i}]' not in out:
                out = out.replace(marker, f'{marker} [C{i}]', 1)
                break
    return out

# V145.5 — professional brief workflow helpers

def brief_case_understanding(text: str) -> dict:
    """Conservative, extractive pre-draft understanding; never invents facts."""
    text = str(text or '').strip()
    sentences = [s.strip() for s in re.split(r'(?<=[؟.!؛])\s+|[\r\n]+', text) if len(s.strip()) >= 20]
    def pick(pattern, limit=6):
        out=[]
        for s in sentences:
            if re.search(pattern, s, re.I) and s not in out:
                out.append(s[:500])
            if len(out)>=limit: break
        return out
    parties = pick(r'خواهان|خوانده|شاکی|مشتکی|موکل|موجر|مستأجر|زوج|زوجه|خواهان|خوانده')
    claims = pick(r'خواسته|مطالبه|تقاضا|درخواست|ادعا|دفاع|محکومیت|الزام|اعتراض|فسخ|ابطال|اعسار|تقسیط|پرداخت|دین|خسارت|تخلیه')
    evidence = pick(r'سند|مدرک|رسید|قرارداد|اظهارنامه|شهادت|کارشناس|پیوست|گواهی|دادنامه|رأی')
    dates = pick(r'تاریخ|مورخ|سررسید|ابلاغ|مهلت|روز|ماه|سال')
    refs = pick(r'ماده\s*[۰-۹0-9]+|اصل\s*[۰-۹0-9]+|قانون\s+')
    issues=[]
    for label, pat in [
        ('طرفین و سمت‌ها', r'خواهان|خوانده|شاکی|مشتکی|موکل|موجر|مستأجر|زوج|زوجه'),
        ('خواسته/ادعا', r'خواسته|مطالبه|تقاضا|درخواست|ادعا|محکومیت|الزام'),
        ('دفاع/ایراد', r'دفاع|اعتراض|ایراد|جعل|پرداخت|عدم تحویل|بطلان|فسخ'),
        ('ادله', r'سند|مدرک|رسید|قرارداد|اظهارنامه|شهادت|کارشناس|گواهی'),
        ('مبنای قانونی', r'ماده\s*[۰-۹0-9]+|اصل\s*[۰-۹0-9]+|قانون\s+'),
    ]:
        if re.search(pat, text, re.I): issues.append(label)
    missing=[]
    for label, arr in [('طرفین و سمت‌ها',parties),('خواسته/ادعا',claims),('ادله',evidence),('تاریخ‌های کلیدی',dates),('مبنای قانونی صریح',refs)]:
        if not arr: missing.append(label)
    return {'parties':parties,'claims':claims,'evidence':evidence,'dates':dates,'refs':refs,'issues':issues,'missing':missing}


def argument_matrix(text: str, sources=None, support_text: str = '') -> list:
    """Build a conservative claim→fact→evidence→rule→application→request matrix.

    The function only connects material that is explicitly present in the user's
    text/source pack. Missing links stay blank and are reported as gaps; no legal
    conclusion or rebuttal is invented.
    """
    # Claims must come from the active draft. Optional support_text (e.g. the
    # connected case file) may supply facts/evidence, but must never create new
    # claims that silently enter the matrix.
    text = str(text or '').strip()
    support_text = str(support_text or '').strip()
    u = brief_case_understanding(text)
    support_u = brief_case_understanding(support_text) if support_text else {}
    raw_claims = u.get('claims', [])[:20]
    # Keep substantive propositions in the matrix; headings/requests/legal-reference
    # declarations are supporting fields, not separate legal arguments.
    claims = []
    for c in raw_claims:
        c_norm = str(c or '').strip()
        if re.search(r'^\s*(?:خواسته|تقاضا|درخواست)\s*[:：]', c_norm):
            continue
        if re.search(r'^(?:اصل|ماده|تبصره|بند)\s*[۰-۹0-9]+.*(?:قانون|مبنای قانونی)', c_norm):
            continue
        if re.search(r'\b(?:مبنای قانونی|مستند قانونی)\b', c_norm) and not re.search(r'(?:مطالبه|دفاع|اعتراض|الزام|فسخ|ابطال|پرداخت)', c_norm):
            continue
        if c_norm not in claims:
            claims.append(c_norm)
        if len(claims) >= 10:
            break
    evidence = list(u.get('evidence', [])[:15])
    for item in support_u.get('evidence', [])[:15]:
        if item not in evidence:
            evidence.append(item)
    refs = list(u.get('refs', [])[:10])
    for item in support_u.get('refs', [])[:10]:
        if item not in refs:
            refs.append(item)
    source_items = list(sources or [])

    # Explicit request/relief statements, kept separate from ordinary claims.
    request_re = r'خواسته|تقاضا|درخواست|محکومیت|الزام|رد دعوا|نقض|اصلاح|تأیید|فسخ|ابطال|تخلیه|پرداخت'
    requests = [x for x in u.get('claims', []) if re.search(request_re, x)]
    if not requests:
        requests = [x for x in re.split(r'(?<=[؟.!؛])\s+|[\r\n]+', str(text or ''))
                    if re.search(request_re, x) and len(x.strip()) >= 18][:6]

    def terms(s):
        return set(re.findall(r'[آ-یA-Za-z]{3,}', str(s or '')))

    rows=[]
    for i, claim in enumerate(claims, 1):
        cterms = terms(claim)
        ev = [e for e in evidence if len(cterms & terms(e)) >= 1][:2]
        # A fact is a sentence without a legal/request-heavy verb where possible.
        fact_pool = '\n'.join(x for x in (text, support_text) if x)
        facts = [s for s in re.split(r'(?<=[؟.!؛])\s+|[\r\n]+', fact_pool)
                 if len(s.strip()) >= 20 and len(cterms & terms(s)) >= 1
                 and not re.search(request_re, s)][:2]

        matched_refs = [r for r in refs if len(cterms & terms(r)) >= 1][:2]
        # If the input contains only one explicit legal-reference statement,
        # expose it as a clearly labelled candidate rather than silently
        # claiming that the rule governs the particular claim.
        rule_candidate = refs[0] if len(refs) == 1 else ''
        citations=[]
        for sidx, src_item in enumerate(source_items,1):
            article=str(src_item.get('article') or src_item.get('ماده') or '').strip()
            ruling=str(src_item.get('ruling_number') or '').strip()
            title=str(src_item.get('title') or src_item.get('law') or src_item.get('name') or '')
            hay=f'{article} {ruling} {title}'
            if article and any(re.search(r'ماده\s*'+re.escape(article), r) for r in matched_refs):
                citations.append(f'[C{sidx}]')
            elif ruling and ruling in ' '.join(matched_refs):
                citations.append(f'[C{sidx}]')
            elif len(cterms & terms(hay)) >= 1 and matched_refs:
                citations.append(f'[C{sidx}]')

        rule = matched_refs[0] if matched_refs else (f'مبنای قانونی ذکرشده در متن: {rule_candidate}' if rule_candidate else '')
        req = next((r for r in requests if len(cterms & terms(r)) >= 1), '')
        # Extract an explicit application sentence when the user actually wrote one.
        # Never infer the legal application merely from coexistence of a fact and a rule.
        application = ''
        application_patterns = r'(?:با توجه به|با عنایت به|نظر به|لذا|بنابراین|از این رو|در نتیجه|اعمال|مستفاد از).{0,260}'
        for sentence in re.split(r'(?<=[؟.!؛])\s+|[\r\n]+', str(text or '')):
            sentence = sentence.strip()
            if len(sentence) >= 25 and re.search(application_patterns, sentence, re.I):
                if len(cterms & terms(sentence)) >= 1 or (rule and any(tok in sentence for tok in ('ماده','قانون','قاعده'))):
                    application = sentence[:500]
                    break
        gaps=[]
        if not facts: gaps.append('واقعیت مرتبط')
        if not ev: gaps.append('دلیل/مدرک')
        if not rule and not citations: gaps.append('قاعده یا مستند قانونی')
        if not application: gaps.append('نحوه اعمال قاعده بر واقعیت')
        if not req: gaps.append('خواسته مرتبط')
        status = ('نیازمند مستند' if not ev and not citations else ('کامل نیست' if gaps else 'آماده بازبینی'))
        rows.append({
            'id': i,
            'claim': claim,
            'fact': facts[0] if facts else '',
            'facts': facts,
            'evidence': ev,
            'rule': rule,
            'legal_refs': matched_refs,
            'application': application,
            'request': req,
            'citations': citations,
            'gaps': gaps,
            'status': status,
        })
    return rows


def validate_brief(text: str, sources=None) -> dict:
    """Final deterministic pre-export validation."""
    text=str(text or '').strip(); sources=sources or []
    placeholders=bool(re.search(r'\.{4,}|…{2,}|_{4,}|\.{3}', text))
    cids=[int(x) for x in re.findall(r'\[C(\d+)\]', text)]
    invalid=sorted({x for x in cids if x<1 or x>len(sources)})
    source_markers=sorted(set(cids))
    return {
        'placeholder': placeholders,
        'citation_count': len(cids),
        'invalid_citations': invalid,
        'unused_sources':[i for i in range(1,len(sources)+1) if i not in source_markers],
        'has_topic': bool(re.search(r'موضوع\s*[:：]', text)),
        'has_request': bool(re.search(r'خواسته|تقاضا|درخواست|محکومیت|الزام', text)),
        'has_authority': bool(re.search(r'ریاست|شعبه|مرجع', text)),
        'has_evidence': bool(re.search(r'دلیل|مدرک|سند|شهادت|کارشناس|پیوست|مستند|استناد|رسید|اظهارنامه|گواهی', text)),
        'overconfident': bool(re.search(r'قطعاً محکوم|حتماً برنده|بدون شک|صددرصد|نتیجه قطعی', text)),
    }


def cleanup_brief_text(text: str) -> str:
    """Safe presentation cleanup only; no legal rewriting."""
    out=re.sub(r'[ \t]+\n','\n',str(text or ''))
    out=re.sub(r'\n{3,}','\n\n',out).strip()
    out=re.sub(r'^(\s*\d+\))\s+',r'\1 ',out,flags=re.M)
    out=re.sub(r'\[C(\d+)\]\s*\[C\1\]',r'[C\1]',out)
    return out


def detailed_diff_summary(old: str, new: str) -> dict:
    import difflib
    old_lines=old.splitlines(); new_lines=new.splitlines()
    added=sum(1 for x in difflib.ndiff(old_lines,new_lines) if x.startswith('+ '))
    removed=sum(1 for x in difflib.ndiff(old_lines,new_lines) if x.startswith('- '))
    changed=max(0,min(added,removed))
    old_c=set(re.findall(r'\[C\d+\]',old)); new_c=set(re.findall(r'\[C\d+\]',new))
    return {'added':added,'removed':removed,'changed':changed,'citations_added':sorted(new_c-old_c),'citations_removed':sorted(old_c-new_c)}


def extract_opposing_claims(text: str, limit: int = 12) -> list:
    """Extract explicit, reviewable claims from an opposing brief without inventing responses."""
    text = str(text or '').strip()
    if not text:
        return []
    blocks = [b.strip() for b in re.split(r'\n\s*\n|^\s*(?:\d+[\)\.\-]|[۰-۹]+[\)\.\-])\s*', text, flags=re.M) if b.strip()]
    out = []
    claim_words = r'ادعا|اظهار|مدعی|درخواست|تقاضا|دفاع|ایراد|اعتراض|عدم|وجود|پرداخت|بطلان|فسخ|الزام|محکومیت|خسارت|دین|طلب|چک|قرارداد|اجاره|تخلیه|اعسار|تقسیط'
    for block in blocks:
        sentences = [s.strip() for s in re.split(r'(?<=[؟.!؛])\s+|[\r\n]+', block) if len(s.strip()) >= 18]
        candidates = [s for s in sentences if re.search(claim_words, s, re.I)]
        chosen = candidates[0] if candidates else (sentences[0] if sentences else block)
        chosen = re.sub(r'^\s*(?:\d+[\)\.\-]|[۰-۹]+[\)\.\-])\s*', '', chosen).strip()
        if chosen and chosen not in out:
            out.append(chosen[:700])
        if len(out) >= limit:
            break
    return out


def opposing_response_matrix(opposing_text: str, case_text: str = '', sources=None) -> list:
    """Build a conservative response matrix: opponent claim + available case support + source refs.
    It deliberately leaves the legal response blank so the bot does not invent a rebuttal.
    """
    claims = extract_opposing_claims(opposing_text)
    u = brief_case_understanding(case_text)
    evidence = u.get('evidence', [])
    refs = u.get('refs', [])
    rows=[]
    for i, claim in enumerate(claims, 1):
        terms=set(re.findall(r'[آ-یA-Za-z]{4,}', claim))
        ev=[e for e in evidence if len(terms & set(re.findall(r'[آ-یA-Za-z]{4,}', e))) >= 1][:2]
        citations=[]
        for sidx, src in enumerate(sources or [], 1):
            article=str(src.get('article') or src.get('ماده') or '')
            ruling=str(src.get('ruling_number') or '')
            if article and any(re.search(r'ماده\s*'+re.escape(article), r) for r in refs):
                citations.append(f'[C{sidx}]')
            elif ruling and ruling in ' '.join(refs):
                citations.append(f'[C{sidx}]')
        rows.append({'id':i, 'claim':claim, 'response':'', 'evidence':ev,
                     'citations':citations, 'status':'آماده پاسخ' if (ev or citations) else 'بدون مستند پاسخ'})
    return rows


def apply_opposing_responses(rows: list, response_text: str) -> list:
    """Apply explicitly supplied responses such as «پاسخ 2: ...» to extracted claims."""
    mapping = {}
    for m in re.finditer(r'(?m)^\s*(?:پاسخ|جواب)\s*([0-9۰-۹]+)\s*[:：]\s*(.+?)(?=\n\s*(?:پاسخ|جواب)\s*[0-9۰-۹]+\s*[:：]|\Z)', str(response_text or ''), re.S):
        n = int(str(m.group(1)).translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹','0123456789')))
        mapping[n] = m.group(2).strip()
    out=[]
    for row in rows or []:
        r=dict(row)
        if r.get('id') in mapping:
            r['response']=mapping[r['id']][:1000]
            r['status']='پاسخ ثبت شد'
        out.append(r)
    return out


def opposing_response_outline(rows: list) -> str:
    """Create a fillable response outline; it never writes missing legal reasoning."""
    parts=['پیش‌نویس ساختاری پاسخ به لایحه طرف مقابل','',
           'این متن صرفاً اسکلت تنظیم لایحه است و پاسخ‌های ثبت‌نشده باید توسط کاربر تکمیل و بازبینی شوند.','']
    for r in rows or []:
        parts += [f"{r['id']}) در پاسخ به ادعای طرف مقابل:", r['claim'],
                  f"پاسخ: {r.get('response') or '[پاسخ شما درج شود]'}",
                  f"مستند/دلیل: {' | '.join(r.get('evidence') or []) or '[دلیل درج شود]'}",
                  f"مستند قانونی: {' '.join(r.get('citations') or []) or '[منبع درج شود]'}", '']
    return '\n'.join(parts).strip()


def brief_gap_analysis(text: str, case_text: str = '', sources=None, brief_type: str = '', template_key: str = '', opposing_text: str = '') -> dict:
    """Find high-value missing links before final drafting.

    This is a conservative completeness check, not legal reasoning. It combines
    explicit document requirements, the argument matrix, citation validation,
    and internal-consistency findings. It never fills a missing legal argument.
    """
    text = str(text or '').strip()
    case_text = str(case_text or '').strip()
    selected = list(sources or [])
    u = brief_case_understanding('\n'.join(x for x in (case_text, text) if x))
    # The matrix must see both the active draft and the connected case.
    # Otherwise evidence/facts that live only in the case can be reported as
    # missing even though they are available to the brief workflow.
    matrix = argument_matrix(text, selected, support_text=case_text)
    validation = validate_brief(text, selected) if text else {
        'has_topic': False, 'has_request': False, 'has_authority': False,
        'has_evidence': False, 'citation_count': 0, 'invalid_citations': [],
        'placeholder': False, 'overconfident': False, 'unused_sources': []}

    items = []
    def add(key, severity, label, detail):
        items.append({'key': key, 'severity': severity, 'label': label, 'detail': detail})

    if not validation.get('has_topic'):
        add('topic', 'high', 'موضوع/مسئله', 'موضوع یا مسئله اصلی لایحه صریح نیست.')
    if not validation.get('has_request'):
        add('request', 'high', 'خواسته/تقاضا', 'خواسته یا تقاضای پایانی به‌صورت روشن پیدا نشد.')
    if not validation.get('has_authority'):
        add('authority', 'medium', 'مرجع رسیدگی', 'مرجع رسیدگی در متن به‌طور روشن مشخص نشده است.')
    if not validation.get('has_evidence'):
        add('evidence', 'high', 'دلیل/مدرک', 'برای ادعاهای متن، دلیل یا مدرک صریح کافی پیدا نشد.')
    if not selected:
        add('sources', 'medium', 'منابع حقوقی', 'هیچ منبع تأییدشده‌ای برای این لایحه انتخاب نشده است.')
    if validation.get('invalid_citations'):
        add('citation', 'high', 'Citation', 'برخی ارجاعات متن به منبع انتخاب‌شده متناظر ندارند.')
    if validation.get('placeholder'):
        add('placeholder', 'high', 'جای‌خالی', 'یک یا چند placeholder/جای‌خالی هنوز در متن باقی مانده است.')
    if not matrix and validation.get('has_request') and not validation.get('has_evidence'):
        add('matrix:evidence-empty', 'high', 'دلیل/مدرک', 'ادعا/خواسته در متن دیده می‌شود، اما برای ساخت ماتریس استدلال دلیل یا مدرک صریحی پیدا نشد.')

    matrix_gaps = {}
    for row in matrix:
        for gap in row.get('gaps') or []:
            matrix_gaps[gap] = matrix_gaps.get(gap, 0) + 1
    gap_labels = {
        'واقعیت مرتبط': ('medium', 'واقعیت مرتبط', 'حداقل یک ادعا به واقعیت مشخص پرونده متصل نشده است.'),
        'دلیل/مدرک': ('high', 'دلیل/مدرک', 'حداقل یک ادعا دلیل یا مدرک صریح ندارد.'),
        'قاعده یا مستند قانونی': ('medium', 'قاعده/مستند قانونی', 'حداقل یک ادعا مبنای قانونی صریح ندارد.'),
        'نحوه اعمال قاعده بر واقعیت': ('high', 'اعمال قاعده', 'برای حداقل یک ادعا نحوه ارتباط قاعده حقوقی با واقعیت پرونده ثبت نشده است.'),
        'خواسته مرتبط': ('medium', 'خواسته مرتبط', 'حداقل یک ادعا به خواسته مشخص متصل نشده است.'),
    }
    for gap, count in matrix_gaps.items():
        sev, label, detail = gap_labels.get(gap, ('medium', gap, f'{count} مورد از این بخش نیازمند تکمیل است.'))
        add('matrix:' + gap, sev, label, detail)

    # Explicitly surface case-level missing information without duplicating
    # every low-level detector already shown elsewhere.
    for missing in u.get('missing') or []:
        if missing in {'طرفین و سمت‌ها', 'خواسته/ادعا', 'ادله', 'تاریخ‌های کلیدی'}:
            add('case:' + missing, 'medium', missing, f'اطلاعات «{missing}» در متن پرونده/لایحه به‌قدر کافی استخراج نشد.')

    if opposing_text.strip():
        opposing_rows = opposing_response_matrix(opposing_text, case_text, selected)
        unresolved = [r for r in opposing_rows if not str(r.get('response') or '').strip()]
        if unresolved:
            add('opposing:unresolved', 'high', 'ادعاهای بدون پاسخ', f'{len(unresolved)} ادعای استخراج‌شده از لایحه طرف مقابل هنوز پاسخ صریح ندارد.')

    consistency = brief_consistency_check(text, case_text)
    if consistency.get('findings'):
        add('consistency', 'high' if consistency.get('high') else 'medium', 'تناقض داخلی', f"{consistency['count']} مورد تعارض یا مقدار بالقوه متعارض برای بازبینی وجود دارد.")

    # De-duplicate by key and keep the strongest severity.
    order = {'high': 0, 'medium': 1, 'low': 2}
    merged = {}
    for item in items:
        old = merged.get(item['key'])
        if old is None or order[item['severity']] < order[old['severity']]:
            merged[item['key']] = item
    items = list(merged.values())
    items.sort(key=lambda x: (order[x['severity']], x['label']))

    return {
        'items': items,
        'count': len(items),
        'high': sum(1 for x in items if x['severity'] == 'high'),
        'medium': sum(1 for x in items if x['severity'] == 'medium'),
        'ready': not any(x['severity'] == 'high' for x in items),
        'matrix_rows': len(matrix),
        'validation': validation,
        'consistency': consistency,
    }


def format_gap_analysis(report: dict) -> str:
    report = report or {}
    items = report.get('items') or []
    if not items:
        return '🟢 تحلیل خلأ: مورد مهمی برای تکمیل پیش از نگارش نهایی پیدا نشد. این نتیجه جایگزین بازبینی حقوقی نیست.'
    lines = [f"🧩 تحلیل خلأ پیش از نگارش نهایی — {len(items)} مورد", '']
    for i, item in enumerate(items, 1):
        icon = '🔴' if item.get('severity') == 'high' else '🟡'
        lines.append(f"{icon} {i}. {item.get('label','')}: {item.get('detail','')}")
    lines += ['', f"وضعیت: {'🟠 نیازمند تکمیل' if report.get('high') else '🟡 آماده بازبینی'}"]
    lines.append('این گزارش فقط کمبودهای اطلاعاتی/ساختاری را علامت می‌زند و پاسخ یا استدلال حقوقی جدید اختراع نمی‌کند.')
    return '\n'.join(lines)

# V145.6 — internal consistency / contradiction checks

def _normalize_digits(value: str) -> str:
    return str(value or '').translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789'))


def _normalize_name(value: str) -> str:
    value = str(value or '').replace('ي', 'ی').replace('ك', 'ک').replace('\u200c', ' ')
    value = re.sub(r'\s+', ' ', value).strip(' ،؛:.-')
    return value


def brief_consistency_check(text: str, case_text: str = '') -> dict:
    """Conservative contradiction detector for brief/case text.

    It reports only explicit textual conflicts or potentially conflicting values;
    it does not decide which statement is true.
    """
    text = str(text or '').strip()
    case_text = str(case_text or '').strip()
    combined = '\n'.join(x for x in (case_text, text) if x)
    findings = []

    def add(kind, severity, message, snippets=None):
        item = {'kind': kind, 'severity': severity, 'message': message}
        if snippets:
            item['snippets'] = list(dict.fromkeys(str(x).strip() for x in snippets if str(x).strip()))[:3]
        findings.append(item)

    # Explicit payment polarity conflict.
    positive = re.findall(r'[^\n.؟؛]{0,100}(?:پرداخت\s+(?:شد|گردید|شده|انجام\s+شد)|تسویه\s+(?:شد|گردید|شده)|وجه\s+پرداخت\s+شد)[^\n.؟؛]{0,100}', combined)
    negative = re.findall(r'[^\n.؟؛]{0,100}(?:پرداخت\s+نشده|عدم\s+پرداخت|پرداخت\s+نکرد|تسویه\s+نشده|باقی(?:\s+مانده)?\s+است|بدهکار\s+است)[^\n.؟؛]{0,100}', combined)
    if positive and negative:
        add('payment', 'high', 'عبارات صریحاً متفاوت درباره پرداخت/عدم پرداخت دیده شد؛ مشخص کنید هر عبارت مربوط به کدام مبلغ یا مرحله است.', positive + negative)

    # Same person explicitly assigned incompatible party roles.
    role_matches = re.findall(r'([آ-یA-Za-z][آ-یA-Za-z\u200c\s]{2,60}?)\s+(?:به عنوان|بعنوان)?\s*(خواهان|خوانده|شاکی|مشتکی[‌ ]?عنه|موجر|مستأجر|زوج|زوجه)\b', combined)
    by_name = {}
    for name, role in role_matches:
        n = _normalize_name(name)
        if len(n) < 3:
            continue
        by_name.setdefault(n, set()).add(role.replace('\u200c', ' '))
    incompatible = []
    incompatible_pairs = [({'خواهان','خوانده'}), ({'شاکی','مشتکی عنه'}), ({'موجر','مستأجر'}), ({'زوج','زوجه'})]
    for name, roles in by_name.items():
        for pair in incompatible_pairs:
            if pair.issubset(roles):
                incompatible.append(f'{name}: ' + ' / '.join(sorted(pair)))
    if incompatible:
        add('party_role', 'high', 'یک نام/شخص در متن با نقش‌های ناسازگار معرفی شده است؛ نام و سمت هر طرف کنترل شود.', incompatible)

    # Same event label with more than one explicit date.
    date_pat = r'(?:13|14)[0-9۰-۹]{2}[/-][0-9۰-۹]{1,2}[/-][0-9۰-۹]{1,2}'
    event_patterns = {
        # Keep the date window narrow enough that a second event in the same
        # sentence is not incorrectly attached to the first event.
        'قرارداد': r'قرارداد[^\n.؟؛]{0,35}' + date_pat,
        'سررسید': r'سررسید[^\n.؟؛]{0,35}' + date_pat,
        'ابلاغ': r'(?:ابلاغ|تاریخ ابلاغ)[^\n.؟؛]{0,35}' + date_pat,
        'اظهارنامه': r'اظهارنامه[^\n.؟؛]{0,35}' + date_pat,
        'دادخواست': r'دادخواست[^\n.؟؛]{0,35}' + date_pat,
    }
    for label, pat in event_patterns.items():
        snippets = re.findall(pat, combined)
        dates = []
        for s in snippets:
            ds = [_normalize_digits(x) for x in re.findall(date_pat, s)]
            dates.extend(ds)
        unique_dates = list(dict.fromkeys(dates))
        if len(unique_dates) > 1:
            add('date', 'medium', f'برای «{label}» بیش از یک تاریخ صریح دیده شد؛ بررسی کنید آیا مربوط به یک رویداد واحد است یا رویدادهای متفاوت.', snippets)

    # Same labelled monetary item with different explicit amounts.
    amount_pat = r'\d[\d۰-۹]*(?:[,.]\d[\d۰-۹]*)*\s*(?:میلیون|میلیارد|هزار)?\s*(?:تومان|ریال)'
    money_labels = {
        'مبلغ قرارداد': r'[^\n.؟؛]{0,70}(?:مبلغ\s+قرارداد|ثمن\s+قرارداد)[^\n.؟؛]{0,100}',
        'مبلغ خواسته': r'[^\n.؟؛]{0,70}(?:مبلغ\s+خواسته|خواسته\s+به\s+مبلغ)[^\n.؟؛]{0,100}',
        'مهریه': r'[^\n.؟؛]{0,70}مهریه[^\n.؟؛]{0,100}',
        'دین': r'[^\n.؟؛]{0,70}(?:دین|طلب|بدهی)[^\n.؟؛]{0,100}',
    }
    for label, pat in money_labels.items():
        snippets = re.findall(pat, combined)
        vals = []
        for s in snippets:
            vals.extend(_normalize_digits(x).replace(',', '').replace('،', '') for x in re.findall(amount_pat, s))
        unique_vals = list(dict.fromkeys(vals))
        if len(unique_vals) > 1:
            add('amount', 'medium', f'برای «{label}» بیش از یک مبلغ صریح دیده شد؛ مشخص کنید کدام مبلغ مربوط به کدام مرحله/ادعاست.', snippets)

    # Conflicting explicit statements using the same simple predicate.
    polarity_pairs = [
        (r'(?:قرارداد|عقد)\s+(?:معتبر|صحیح)\s+است', r'(?:قرارداد|عقد)\s+(?:باطل|بی\s*اعتبار)\s+است', 'اعتبار قرارداد'),
        (r'(?:دین|بدهی|طلب)\s+(?:وجود\s+)?دارد', r'(?:دین|بدهی|طلب)\s+(?:وجود\s+)?ندارد', 'وجود دین/بدهی'),
        (r'تحویل\s+(?:داده\s+شد|شده|گردید)', r'(?:تحویل\s+)?داده\s+نشده|تحویل\s+نگرفته', 'تحویل'),
    ]
    for pos, neg, label in polarity_pairs:
        ps = re.findall(r'[^\n.؟؛]{0,80}' + pos + r'[^\n.؟؛]{0,80}', combined)
        ns = re.findall(r'[^\n.؟؛]{0,80}' + neg + r'[^\n.؟؛]{0,80}', combined)
        if ps and ns:
            add('predicate', 'high', f'عبارات متعارض درباره «{label}» دیده شد؛ مشخص کنید آیا مربوط به زمان/موضوع متفاوت هستند.', ps + ns)

    # De-duplicate exact findings.
    seen = set(); unique = []
    for item in findings:
        key = (item['kind'], item['message'])
        if key not in seen:
            seen.add(key); unique.append(item)
    high = sum(1 for x in unique if x['severity'] == 'high')
    return {'count': len(unique), 'high': high, 'findings': unique, 'status': 'conflict' if unique else 'clear'}


def format_consistency_report(report: dict) -> str:
    """Telegram-friendly report for internal consistency findings."""
    report = report or {}
    findings = report.get('findings') or []
    if not findings:
        return '🟢 کنترل تناقضات: تعارض صریحی در متن پیدا نشد. این نتیجه به معنی صحت factual یا حقوقی متن نیست و بازبینی وکیل همچنان لازم است.'
    lines = [f'⚠️ کنترل تناقضات داخلی — {len(findings)} مورد قابل بررسی', '']
    for i, item in enumerate(findings, 1):
        sev = '🔴' if item.get('severity') == 'high' else '🟡'
        lines.append(f'{sev} {i}. {item.get("message", "") }')
        for s in (item.get('snippets') or [])[:2]:
            lines.append(f'   «{s[:260]}»')
    lines += ['', 'این گزارش فقط تعارض‌های صریح یا مقادیر بالقوه متعارض را علامت می‌زند و درباره درست یا نادرست بودن هیچ‌یک تصمیم نمی‌گیرد.']
    return '\n'.join(lines)
