import hashlib,uuid,re,os,shutil,subprocess
from pathlib import Path
try:
    import pymupdf as fitz
except ImportError:
    import fitz  # legacy
from docx import Document
from PIL import Image, ImageOps, ImageFilter, ImageEnhance
from .config import UPLOAD_DIR,MAX_FILE_MB,OCR_ENABLED,TESSERACT_CMD,TESSERACT_LANG,MAX_TEXT_CHARS,MAX_DOCUMENT_PAGES
from .legal_text_cleanup import cleanup_legal_text
from .source_segmentation import segment_document_pages

PERSIAN_RE = re.compile(r'[\u0600-\u06ff]')
DIGIT_RE = re.compile(r'[0-9۰-۹]')
LATIN_RE = re.compile(r'[A-Za-z]')

def sha256(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b): h.update(b)
    return h.hexdigest()

def clean_fa(t):
    if not t:return ''
    t=t.replace('\ufeff','').replace('\u200c','‌')
    t=t.replace('ي','ی').replace('ى','ی').replace('ك','ک')
    t=t.replace('ـ','')
    # OCR exception for the Arabic/Persian lam-alef ligature.
    # Some Persian scans render «لا» as a typographic joined glyph and
    # Tesseract can occasionally read it as the standalone sequence «ال».
    # Only repair an EXACT standalone token «ال» (or «ا ل»), never a substring
    # inside words such as «سالم» or «الزام». This deliberately conservative
    # rule is the first hypothesis; if testing disproves it, remove it.
    t=re.sub(r'(?<!\S)ا\s+ل(?!\S)', 'لا', t)
    # Normalize Arabic presentation-form lam-alef characters if an OCR/PDF
    # text layer exposes the actual ligature rather than two letters.
    t=t.translate(str.maketrans({
        '\ufefb':'لا','\ufefc':'لا','\ufef7':'لا','\ufef8':'لا',
        '\ufef5':'لا','\ufef6':'لا'
    }))
    t=re.sub(r'[|_]{1,}', ' ', t)
    # Normalize spaces but keep line boundaries.
    t=re.sub(r'[ \t]+', ' ', t)
    t=re.sub(r' *\n *', '\n', t)
    t=re.sub(r'\n{3,}','\n\n',t)
    return cleanup_legal_text(t)

def _text_quality(t):
    """Heuristic score for a PDF native text layer."""
    if not t:return 0.0
    s=re.sub(r'\s+','',t)
    if not s:return 0.0
    fa=len(PERSIAN_RE.findall(s))/len(s)
    digits=len(DIGIT_RE.findall(s))/len(s)
    latin=len(LATIN_RE.findall(s))/len(s)
    runs=re.findall(r'[0-9۰-۹]{8,}', s)
    long_digit_penalty=min(0.45, 0.08*len(runs))
    weird=len(re.findall(r'[\uFFFD\uFFFE\uFFFF]',s))/len(s)
    score=0.60*min(fa/0.18,1.0)+0.15*min((fa+latin)/0.22,1.0)+0.25*(1-long_digit_penalty-weird)
    return max(0.0,min(1.0,score))

def _looks_broken(t):
    if len(t)<40:return True
    q=_text_quality(t)
    s=re.sub(r'\s+','',t)
    digit_tokens=re.findall(r'[0-9۰-۹]{9,}',s)
    fa=len(PERSIAN_RE.findall(s))/max(1,len(s))
    # Long numeric runs are normal in some documents, so require more than
    # one symptom before forcing OCR.
    return q < 0.56 or len(digit_tokens) >= 10 or (len(digit_tokens)>=4 and fa < 0.18)

def _native_layout_text(page):
    """Rebuild PDF text using word coordinates instead of PyMuPDF's linear order.

    This is important for Persian/RTL PDFs: get_text('text') can place a value
    before its label even when the PDF looks perfectly normal on screen.
    """
    words=page.get_text('words', sort=False)
    if not words:
        return ''
    # Group words into visual lines. A line is represented by its block/line
    # identifiers; words are then ordered from the right edge toward the left.
    groups={}
    for w in words:
        x0,y0,x1,y1,txt,block_no,line_no,word_no=w
        if not txt.strip():
            continue
        key=(block_no,line_no)
        groups.setdefault(key,[]).append((x0,y0,x1,y1,txt,word_no))
    lines=[]
    for key,items in groups.items():
        y=min(x[1] for x in items)
        height=max(x[3] for x in items)-y
        # Most Persian document lines are visually RTL. Sorting by right edge
        # also keeps labels before their numeric values.
        items=sorted(items,key=lambda x:(-x[2], x[5]))
        line=' '.join(x[4] for x in items)
        lines.append((y,key[0],key[1],height,line))
    lines.sort(key=lambda x:(x[0],-x[1],-x[2]))
    out=[]
    prev_y=None
    prev_block=None
    prev_h=12
    for y,block,line,h,text in lines:
        if prev_y is not None:
            gap=y-prev_y
            # Preserve paragraph-ish gaps without creating a blank line for
            # every normal line.
            if gap>max(8.0,prev_h*1.8) or block!=prev_block and gap>prev_h*1.25:
                out.append('')
        out.append(text)
        prev_y=y;prev_h=h;prev_block=block
    return _normalize_mixed_tokens(clean_fa('\n'.join(out)))


def _normalize_mixed_tokens(text):
    """Fix harmless extraction artifacts without inventing document data."""
    # First split a glued unit such as ریال۱ so the numeric groups can be seen.
    text=re.sub(r'(?P<unit>ریال|تومان)(?P<num>[0-9۰-۹][0-9۰-۹,\.\-]*)',
                r'\g<num> \g<unit>', text)
    # Join digit fragments split by the PDF text layer and normalize separators.
    text=re.sub(r'(?<=[0-9۰-۹])\s+(?=[0-9۰-۹])', '', text)
    text=re.sub(r'\s*([,،/])\s*', r'\1', text)
    # Some RTL PDF generators store comma-separated numeric groups in reverse
    # visual order. Reverse only the characteristic zero-padded form.
    def _fix_amount(m):
        raw=m.group(0)
        groups=raw.split(',')
        if len(groups)>=3 and len(groups[0])==3 and groups[0].startswith(('0','۰')):
            return ','.join(reversed(groups))
        return raw
    text=re.sub(r'(?<![0-9۰-۹])[0-9۰-۹]{1,3}(?:,[0-9۰-۹]{1,3}){2,}(?![0-9۰-۹])',
                _fix_amount, text)
    # Similar RTL storage can reverse a date such as ۱۸/۰۸/۱۴۰۵.
    def _fix_date(m):
        a,b,c=m.group(1),m.group(2),m.group(3)
        if len(c)==4 and len(a)<=2:
            return f'{c}/{b}/{a}'
        return m.group(0)
    text=re.sub(r'([0-9۰-۹]{1,2})/([0-9۰-۹]{1,2})/([0-9۰-۹]{4})', _fix_date, text)
    # Separate a glued field label from a numeric value, e.g. واحد۲۴.
    text=re.sub(r'(?P<word>[^\W\d_]{2,})(?P<num>[0-9۰-۹]{1,})(?=\s|[,،/:.-]|$)',
                r'\g<word> \g<num>', text)
    text=re.sub(r'(?P<num>[0-9۰-۹]{1,})(?P<word>ریال|تومان)',
                r'\g<num> \g<word>', text)
    text=re.sub(r'[ ]{2,}', ' ', text)
    return text

def prepare_image(img, scale=3.0):
    """Stronger preprocessing for phone photos of legal documents."""
    img = ImageOps.exif_transpose(img)
    # Keep color briefly for contrast stats, then grayscale.
    img = img.convert('RGB')
    w, h = img.size
    # Small phone crops need more upscaling; already-large scans less so.
    long_side = max(w, h)
    if long_side < 900:
        auto_scale = 4.0
    elif long_side < 1400:
        auto_scale = 3.2
    elif long_side < 2200:
        auto_scale = 2.6
    else:
        auto_scale = 2.0
    scale = max(float(scale), auto_scale)
    scale = max(1.8, min(scale, 4.0))
    img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
    img = ImageOps.autocontrast(img, cutoff=1)
    gray = img.convert('L')
    gray = ImageEnhance.Contrast(gray).enhance(1.85)
    gray = ImageEnhance.Sharpness(gray).enhance(1.65)
    gray = ImageEnhance.Brightness(gray).enhance(1.05)
    # Light denoise without killing thin Persian dots/diacritics too aggressively.
    gray = gray.filter(ImageFilter.MedianFilter(size=3))
    return gray


def prepare_image_variants(img):
    """Build a few variants; OCR picks the highest-quality text."""
    base_img = ImageOps.exif_transpose(img)
    variants = [prepare_image(base_img)]
    try:
        # High-contrast binary-ish variant helps faded stamps / gray scans.
        g = prepare_image(base_img, scale=3.2)
        from PIL import ImageOps as _IO
        variants.append(_IO.autocontrast(g, cutoff=2))
        # Slightly darker variant for light pencil / gray text.
        variants.append(ImageEnhance.Brightness(g).enhance(0.9))
    except Exception:
        pass
    return variants

def _find_tessdata_dir():
    """Find Tesseract's tessdata directory without assuming one OS path."""
    candidates=[]
    env=os.getenv('TESSDATA_PREFIX','').strip()
    if env:
        p=Path(env)
        candidates.extend([p, p/'tessdata'])
    try:
        import pytesseract
        cmd=TESSERACT_CMD or pytesseract.pytesseract.tesseract_cmd or shutil.which('tesseract')
        if cmd:
            cp=subprocess.run([str(cmd),'--print-parameters'],capture_output=True,text=True,timeout=5)
        # Common Unix/Nix/Replit locations.
        candidates += [
            Path('/usr/share/tesseract-ocr/tessdata'),
            Path('/usr/share/tesseract-ocr/4.00/tessdata'),
            Path('/usr/share/tesseract-ocr/5/tessdata'),
            Path('/usr/share/tessdata'),
            Path('/opt/share/tessdata'),
        ]
    except Exception:
        pass
    for c in candidates:
        try:
            if c.is_dir() and any(c.glob('*.traineddata')):
                return c
        except Exception:
            pass
    return None


def ocr_status():
    """Return an explicit, user/debug-friendly Tesseract installation status."""
    result={
        'enabled': bool(OCR_ENABLED),
        'command': TESSERACT_CMD or '',
        'found': False,
        'version': '',
        'languages': [],
        'requested_languages':[x for x in TESSERACT_LANG.split('+') if x],
        'missing_languages':[],
        'tessdata': '',
        'error': '',
    }
    if not OCR_ENABLED:
        result['error']='OCR_ENABLED خاموش است.'
        return result
    try:
        import pytesseract
        if TESSERACT_CMD:
            pytesseract.pytesseract.tesseract_cmd=TESSERACT_CMD
        cmd=pytesseract.pytesseract.tesseract_cmd
        if cmd=='tesseract':
            resolved=shutil.which('tesseract')
        else:
            resolved=str(cmd) if Path(str(cmd)).exists() else shutil.which(str(cmd))
        result['command']=resolved or str(cmd)
        if not resolved and str(cmd)=='tesseract':
            result['error']='برنامه tesseract در PATH پیدا نشد.'
            return result
        result['version']=str(pytesseract.get_tesseract_version()).strip().splitlines()[0]
        langs=sorted(set(pytesseract.get_languages(config='')))
        result['languages']=langs
        result['missing_languages']=[x for x in result['requested_languages'] if x not in langs]
        td=_find_tessdata_dir()
        if td:
            result['tessdata']=str(td)
        if result['missing_languages']:
            result['error']='زبان/مدل OCR موردنیاز نصب نیست: '+', '.join(result['missing_languages'])
        else:
            result['found']=True
    except Exception as e:
        result['error']=f'{type(e).__name__}: {e}'
    return result


def _ocr_once(img, psm, return_meta=False):
    import pytesseract
    if TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd=TESSERACT_CMD
    status=ocr_status()
    if not status['found']:
        raise RuntimeError(status['error'] or 'Tesseract/OCR آماده نیست.')
    lang='+'.join(status['requested_languages'])
    # Never silently fall back from Persian to English. That can turn a Persian
    # legal document into unusable OCR while making the failure look successful.
    config=f'--oem 1 --psm {psm}'
    if return_meta:
        data=pytesseract.image_to_data(img, lang=lang, config=config, output_type=pytesseract.Output.DICT)
        confs=[]
        for raw in data.get('conf',[]):
            try:
                value=float(raw)
                if value >= 0: confs.append(value)
            except (TypeError,ValueError):
                pass
        text=clean_fa(pytesseract.image_to_string(img,lang=lang,config=config))
        avg=sum(confs)/len(confs) if confs else 0.0
        return text, {'avg_confidence': round(avg,2), 'words': len(confs), 'psm': psm}
    return clean_fa(pytesseract.image_to_string(img,lang=lang,config=config))


def ocr_image(img, diagnostics=None):
    if not OCR_ENABLED:
        if diagnostics is not None: diagnostics['error']='OCR_ENABLED خاموش است.'
        return ''
    try:
        status=ocr_status()
        if diagnostics is not None:
            diagnostics.update({k:status.get(k) for k in ('found','version','languages','requested_languages','missing_languages','tessdata','error')})
        if not status['found']:
            return ''
        variants = prepare_image_variants(img)
        candidates=[]
        for vi, prepared in enumerate(variants):
            for psm in (6, 4, 11, 3):
                try:
                    txt, meta=_ocr_once(prepared, psm, return_meta=True)
                    if txt and len(txt.strip()) >= 20:
                        quality=_text_quality(txt)
                        # Confidence is advisory, not a truth claim: Tesseract's
                        # confidence is combined with Persian-text quality and length.
                        score=(0.62*quality)+(0.28*(meta['avg_confidence']/100.0))+(0.10*min(len(txt)/1800.0,1.0))
                        candidates.append((txt,score,vi,meta))
                except Exception as e:
                    if diagnostics is not None:
                        diagnostics.setdefault('attempt_errors', []).append(
                            f'v{vi}/psm{psm}: {type(e).__name__}: {e}'
                        )
        if not candidates:
            return ''
        best = max(candidates, key=lambda x: (x[1], _text_quality(x[0]), len(x[0])))
        if diagnostics is not None:
            diagnostics['ocr_candidates'] = len(candidates)
            diagnostics['ocr_quality'] = round(_text_quality(best[0]), 3)
            diagnostics['ocr_confidence'] = best[3]['avg_confidence']
            diagnostics['ocr_psm'] = best[3]['psm']
            diagnostics['ocr_variant'] = best[2]
            diagnostics['ocr_selection_score'] = round(best[1], 3)
            diagnostics['ocr_word_count'] = best[3]['words']
        return best[0]
    except Exception as e:
        if diagnostics is not None: diagnostics['error']=f'{type(e).__name__}: {e}'
        return ''


def _render_page(page):
    pix=page.get_pixmap(matrix=fitz.Matrix(4,4),alpha=False)
    return Image.frombytes('RGB',[pix.width,pix.height],pix.samples)


def extract_with_diagnostics(path):
    """Extract text and return a compact diagnostic record for debugging.

    The diagnostics deliberately distinguish native extraction, OCR success,
    OCR unavailable, and native fallback. This prevents a missing Persian OCR
    model from being mistaken for a successful PDF parse.
    """
    if path.stat().st_size > MAX_FILE_MB*1024*1024:
        raise ValueError(f'حجم فایل بیشتر از {MAX_FILE_MB}MB است.')
    ext=path.suffix.lower()
    diag={
        'extension':ext,'pages':0,'native_pages':0,'ocr_pages':0,
        'native_fallback_pages':0,'empty_pages':0,'ocr':ocr_status(),
        'truncated':False,'text_chars':0,'quality':0.0,'status':'unknown','page_diagnostics':[],
    }
    if ext=='.pdf':
        parts=[]
        extracted_pages=[]
        with fitz.open(path) as doc:
            if doc.is_encrypted and not doc.authenticate(''):
                raise ValueError('PDF رمزگذاری‌شده است؛ نسخه‌ای بدون رمز بارگذاری کنید.')
            if len(doc) > MAX_DOCUMENT_PAGES:
                raise ValueError(f'تعداد صفحات سند بیشتر از سقف مجاز ({MAX_DOCUMENT_PAGES}) است.')
            diag['pages']=len(doc)
            for i,page in enumerate(doc):
                native=_native_layout_text(page)
                page_diag={}
                if _looks_broken(native):
                    img=_render_page(page)
                    try:
                        ocr=ocr_image(img,page_diag)
                    finally:
                        img.close()
                    if ocr and len(ocr)>=max(40,int(len(native)*0.25)):
                        txt=ocr; diag['ocr_pages']+=1
                        if page_diag: page_diag['method']='ocr'
                    elif native:
                        txt=native; diag['native_fallback_pages']+=1
                        page_diag['method']='native_fallback'
                    else:
                        txt=''; diag['empty_pages']+=1
                    if page_diag:
                        diag['ocr'].update({k:v for k,v in page_diag.items() if v not in (None,'',[])})
                else:
                    txt=native; diag['native_pages']+=1
                if page_diag:
                    diag['page_diagnostics'].append({'page': i+1, **{k:v for k,v in page_diag.items() if k not in {'attempt_errors'}}})
                elif native:
                    diag['page_diagnostics'].append({'page': i+1, 'method': 'native', 'quality': round(_text_quality(native),3)})
                if txt:
                    extracted_pages.append((i + 1, txt))
                if sum(len(t) for _, t in extracted_pages) > MAX_TEXT_CHARS:
                    diag['truncated']=True; break
        segmented_pages, seg_diag = segment_document_pages(extracted_pages)
        diag['segmentation'] = seg_diag
        parts = [f'[صفحه {page_no}]\n{page_text}' for page_no, page_text in segmented_pages]
        text='\n\n'.join(parts)[:MAX_TEXT_CHARS]
    elif ext=='.docx':
        d=Document(path)
        parts=[p.text for p in d.paragraphs if p.text.strip()]
        for table in d.tables:
            for row in table.rows:
                cells=[clean_fa(c.text.strip()) for c in row.cells]
                line=' | '.join(c for c in cells if c)
                if line: parts.append(line)
        text=clean_fa('\n'.join(parts))[:MAX_TEXT_CHARS]
        diag['pages']=1
    elif ext in {'.jpg','.jpeg','.png','.webp'}:
        with Image.open(path) as img:
            # Bound decompressed image size before scaling/OCR to limit memory abuse.
            if img.width * img.height > 40_000_000:
                raise ValueError('ابعاد تصویر بیش از حد مجاز است؛ تصویر را کوچک‌تر کنید.')
            text=ocr_image(img,diag['ocr'])[:MAX_TEXT_CHARS]
        diag['pages']=1; diag['ocr_pages']=1 if text else 0
    elif ext=='.txt':
        text=clean_fa(path.read_text(encoding='utf8',errors='replace'))[:MAX_TEXT_CHARS]
        diag['pages']=1
    else:
        raise ValueError('فرمت پشتیبانی نمی‌شود')
    # v54: do not apply lexical lam-alef corrections during extraction.
    # The definitive whitelist pass happens at the final user-visible boundary.
    from .text_guard import extraction_quality
    diag['text_chars']=len(text)
    diag['quality']=round(extraction_quality(text),3) if text else 0.0
    if not text.strip(): diag['status']='empty'
    elif diag['ocr_pages'] or diag['native_pages']: diag['status']='ok'
    elif diag['native_fallback_pages']: diag['status']='fallback'
    else: diag['status']='ok'
    return text,diag


def extract(path):
    return extract_with_diagnostics(path)[0]

def new_path(ext):return UPLOAD_DIR/(uuid.uuid4().hex+ext)


def recovery_images(path, max_pages=3):
    """Render up to max_pages from a problematic document for optional AI vision recovery."""
    ext=path.suffix.lower()
    out=[]
    if ext in {'.jpg','.jpeg','.png','.webp'}:
        with Image.open(path) as img:
            p=UPLOAD_DIR/(path.stem+'_ai_recovery.png')
            img.save(p,format='PNG'); out.append(p)
        return out
    if ext=='.pdf':
        with fitz.open(path) as doc:
            for i,page in enumerate(doc):
                if i>=max_pages: break
                native=_native_layout_text(page)
                if not _looks_broken(native): continue
                pix=page.get_pixmap(matrix=fitz.Matrix(2.2,2.2),alpha=False)
                p=UPLOAD_DIR/(f'{path.stem}_ai_recovery_{i+1}.png')
                Image.frombytes('RGB',[pix.width,pix.height],pix.samples).save(p,format='PNG')
                out.append(p)
    return out[:max_pages]
