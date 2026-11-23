import re
from .files import clean_fa
from .ocr_lam_alef import normalize_legal_ocr

DIG='۰۱۲۳۴۵۶۷۸۹'
TRANS=str.maketrans(DIG,'0123456789')


def _digits(s):
    return str(s or '').translate(TRANS)


# Unicode Bidirectional Isolation controls.
# LRI/PDI force numeric tokens to be treated as an independent LTR run inside
# Persian RTL text. They are invisible to the user but prevent visual reversal
# of strings such as ۱۴۰۵/۰۵/۱۱ -> ۱۱/۰۵.
LRI='\u2066'
PDI='\u2069'
NUM_TOKEN_RE=re.compile(r'[0-9۰-۹]+(?:[\/\-.,:٫٬][0-9۰-۹]+)*(?:[%٪])?')

def isolate_numeric_tokens(text):
    """Protect numeric tokens from RTL/LTR bidi reordering.

    This is presentation-only: the actual digits and punctuation are not
    changed. Existing isolation controls are removed first to avoid nesting.
    """
    t=str(text or '').replace(LRI,'').replace(PDI,'')
    return NUM_TOKEN_RE.sub(lambda m: LRI + m.group(0) + PDI, t)


def _sanitize_internal_user_text(text: str) -> str:
    """Remove/translate known internal pipeline markers from user-visible text.

    This is presentation-only. The structured V149-V159 trace is never mutated.
    The rule is intentionally narrow: it targets markers emitted by the legal
    drafting pipeline, not arbitrary English words that might be part of a
    source document or a proper name.
    """
    t = str(text or '')
    # Strategy-frame prose is an internal reasoning scaffold, not part of a
    # user-facing brief. Drop the whole line rather than exposing the marker.
    t = re.sub(r'(?im)^[ \t]*[•\-▪◦]?[ \t]*strategy[_ ]frame[ \t]*:[ \t]*[^\n]*$', '', t)
    t = re.sub(r'(?im)^[ \t]*[•\-▪◦]?[ \t]*application[_ ]frame[ \t]*:[ \t]*[^\n]*$', '', t)
    # Also catch a marker embedded after another sentence on the same line.
    t = re.sub(r'(?i)[ \t]*strategy[_ ]frame[ \t]*:[ \t]*[^\n]*', '', t)
    t = re.sub(r'(?i)[ \t]*application[_ ]frame[ \t]*:[ \t]*[^\n]*', '', t)
    # Remove engine-only footer lines that should never appear in the brief.
    t = re.sub(r'(?im)^\s*🔒\s*V\d+(?:\.\d+)?[^\n]*\n?', '', t)
    # A few legacy labels are safe to translate at the presentation boundary.
    t = re.sub(r'(?i)\bCitation\b', 'استناد', t)
    t = re.sub(r'(?i)\bAPI\b', 'سرویس خارجی', t)
    # Internal V158 markers may appear inside a visible review note. Keep the
    # human-readable message but remove the engine/version label.
    t = re.sub(r'\[V\d+(?:\.\d+)?\s*[—-]\s*', '[', t)
    # Citation keys are trace identifiers, not user-facing prose. Preserve the
    # surrounding legal source text while removing the identifier itself.
    t = re.sub(r'\s*\[?CIT-[A-Za-z0-9_-]+\]?', '', t, flags=re.I)
    # Translate the four internal evidence statuses when they leak into a
    # rendered sentence. The structured value remains English internally.
    status_map = {
        'supported': 'مستند',
        'contradicted': 'متعارض',
        'mixed': 'ترکیبی',
        'unsupported': 'بدون پشتوانه کافی',
    }
    for src, dst in status_map.items():
        t = re.sub(rf'(?i)(?<=وضعیت[:：]\s){re.escape(src)}\b', dst, t)
        t = re.sub(rf'(?i)\bstatus\s*[:：]\s*{re.escape(src)}\b', f'وضعیت: {dst}', t)
    # Standalone internal field labels should never be shown. A Persian label
    # is used for issue, while strategy_frame is removed above.
    t = re.sub(r'(?im)^\s*[•\-▪◦]?\s*issue\s*:\s*', '• مسئله: ', t)
    return t


def normalize_output(text):
    """Conservative final pass for user-visible Persian text.
    Never guesses legal facts; fixes presentation artifacts and removes known
    internal drafting markers without changing the underlying trace."""
    t=clean_fa(text or '')
    t=_sanitize_internal_user_text(t)
    # v54 FINAL lexical OCR pass: this is intentionally the last text-level
    # correction before user-visible output. It only applies certain whitelists.
    t=normalize_legal_ocr(t)
    t=re.sub(r'\u200b+','‌',t)
    t=re.sub(r' {2,}',' ',t)
    t=re.sub(r' *\n *','\n',t)
    # Repair a small, explicit set of common glued legal compounds.
    fixes={
      'وجهالتزام':'وجه التزام','خسارتتأخیرتأدیه':'خسارت تأخیر تأدیه',
      'عدم‌افشا':'عدم افشا','عدم‌نفوذ':'عدم نفوذ','دادخواست‌دهنده':'دادخواست‌دهنده',
      'مادهقانون':'ماده قانون','قانونمدنی':'قانون مدنی','قانونتجارت':'قانون تجارت',
      'خواهانخوانده':'خواهان / خوانده','طرفینقرارداد':'طرفین قرارداد',
    }
    for a,b in fixes.items(): t=t.replace(a,b)
    t=re.sub(r'([،؛:])(?=\S)',r'\1 ',t)
    t=re.sub(r'(?<=\S)([.!؟])(?=\S)',r'\1 ',t)
    t=t.strip()
    # Final presentation safeguard for RTL Persian + LTR numeric strings.
    return isolate_numeric_tokens(t)


def prepare_ai_answer(text):
    """Prepare an AI answer for display without changing its legal meaning.

    This is deliberately a presentation-only pass: normalize Persian typography,
    remove known internal pipeline markers, and collapse only immediately
    repeated identical non-empty lines. It does not invent citations, rewrite
    legal conclusions, or claim that the answer has been fact-checked.
    """
    cleaned = normalize_output(text)
    if not cleaned:
        return ''
    lines = cleaned.splitlines()
    output = []
    previous = None
    for line in lines:
        normalized_line = line.strip()
        if normalized_line and normalized_line == previous:
            continue
        output.append(line)
        previous = normalized_line if normalized_line else None
    # Avoid a visually noisy stack of blank lines while preserving paragraphs.
    cleaned = re.sub(r'\n{3,}', '\n\n', '\n'.join(output)).strip()
    return isolate_numeric_tokens(cleaned)


def suspicious_number(value):
    """Return True only for high-confidence numeric formatting anomalies."""
    s=_digits(value).replace(' ','')
    if not s: return False
    # Dates: month/day cannot be zero or out of Jalali/Gregorian basic bounds.
    m=re.fullmatch(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})',s)
    if m:
        mo,day=int(m.group(2)),int(m.group(3))
        return not (1<=mo<=12 and 1<=day<=31)
    m=re.fullmatch(r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})',s)
    if m:
        a,b=int(m.group(1)),int(m.group(2))
        return not (1<=a<=31 and 1<=b<=12)
    # Obvious reversed grouped amount produced by RTL extraction.
    if re.fullmatch(r'0\d{2}(?:,\d{1,3}){2,}',s): return True
    if re.fullmatch(r'\d{1,3}(?:,\d{1,3}){3,}',s):
        groups=s.split(',')
        if any(len(g)==1 for g in groups[1:]): return True
    return False


def sanitize_result(result):
    """Remove only high-confidence bad numeric fields from the displayed result.
    The raw extracted data remains stored for audit/debugging."""
    r=dict(result or {})
    warnings=[]
    for field in ('dates','amounts'):
        vals=[]
        for item in r.get(field) or []:
            if isinstance(item,dict) and suspicious_number(item.get('value','')):
                warnings.append(f'یک مقدار عددی مشکوک در بخش {field} پیدا شد و برای جلوگیری از ارائه اطلاعات نادرست نمایش داده نشد.')
                continue
            vals.append(item)
        r[field]=vals
    # Clean visible text fields conservatively.
    for field in ('summary','obligations','claims','key_facts','uncertainties','review_points','important_terms','sensitive_clauses','risks','timeline','legal_references'):
        vals=[]
        for item in r.get(field) or []:
            if isinstance(item,dict):
                x=dict(item)
                for k in ('text','fact','claim','item','message','event','context'):
                    if isinstance(x.get(k),str): x[k]=normalize_output(x[k])
                vals.append(x)
            else: vals.append(item)
        r[field]=vals
    # Normalize remaining nested user-visible strings (important terms, risk hits,
    # timeline and legal references) so OCR artifacts cannot leak through a path
    # that was not part of the original summary fields.
    def _clean_nested(value):
        if isinstance(value, dict):
            return {k: (_clean_nested(v) if isinstance(v, (dict, list)) else normalize_output(v) if isinstance(v, str) else v) for k,v in value.items()}
        if isinstance(value, list): return [_clean_nested(v) for v in value]
        return normalize_output(value) if isinstance(value, str) else value
    for field in ('important_terms','sensitive_clauses','risks','timeline','legal_references'):
        r[field]=_clean_nested(r.get(field) or [])
    if warnings: r['output_warnings']=list(dict.fromkeys(warnings))[:4]
    return r


def extraction_quality(text):
    """0..1 confidence score for local extraction; intentionally conservative."""
    t=clean_fa(text or '')
    if not t: return 0.0
    s=re.sub(r'\s+','',t)
    if not s: return 0.0
    fa=len(re.findall(r'[\u0600-\u06ff]',s))/len(s)
    repl=s.count('\ufffd')/len(s)
    long_nums=len(re.findall(r'[0-9۰-۹]{10,}',s))
    glued=len(re.findall(r'[\u0600-\u06ff]{18,}',s))
    score=0.65*min(fa/0.18,1)+0.2*(1-min(repl*20,1))+0.15*(1-min(long_nums/12,1))
    if glued>=4: score-=0.18
    return max(0,min(1,score))


def needs_ai_recovery(text, threshold=0.48):
    return extraction_quality(text) < threshold or text.count('\ufffd')>0
