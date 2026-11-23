"""Conservative Persian legal-text cleanup shared by case and corpus output.

This is display/search normalization, not a claim that the underlying source PDF
was error-free. Only explicit, high-confidence OCR/encoding confusions are fixed.
"""
import re
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
SPACING_LEXICON_PATH = BASE / "persian_spacing_lexicon.json"

COMMON = {
    'اسالمی':'اسلامی','ابالغ':'ابلاغ','اعالم':'اعلام','اصالح':'اصلاح','اصوال':'اصول','امضاء':'امضا',
    'انحالل':'انحلال','تادیه':'تأدیه','تاسیس':'تأسیس','تامین':'تأمین','تایید':'تأیید','تاثیر':'تأثیر',
    'تعیین':'تعیین','دالئل':'دلایل','راسا':'رأساً','رای':'رأی','معامالت':'معاملات','مسول':'مسئول',
    'مسولیت':'مسئولیت','مسئوليت':'مسئولیت','موسسه':'مؤسسه','موسسات':'مؤسسات','موثر':'مؤثر','هیات':'هیئت',
    'قوه قضائیه':'قوه قضائیه','قضایی':'قضائی','قانوناساسی':'قانون اساسی','دادرسیمدنی':'دادرسی مدنی','دادرسیکیفری':'دادرسی کیفری',
    'اختالف':'اختلاف', 'اختالفات':'اختلافات',
    'اعالم':'اعلام', 'اعالء':'اعلاء',
    'اجارهنامه':'اجاره‌نامه', 'اجارهنام':'اجاره‌نامه', 'اجارهنامهای':'اجاره‌نامه‌ای',
    'ولیفقیه':'ولی‌فقیه', 'ولی فقیه':'ولی‌فقیه',
    'شورأی':'شورای', 'شورا ی':'شورای',
    'دارأیی':'دارایی', 'دارایی':'دارایی',
    'اجرأیی':'اجرایی', 'اجرأ':'اجرای',
    'اطالعات':'اطلاعات', 'اطالع':'اطلاع',
    'مییابد':'می‌یابد', 'مییابند':'می‌یابند',
    'سپریشدن':'سپری شدن', 'سپریشده':'سپری شده',
    'مشخصاتخودرو':'مشخصات خودرو', 'شمارهشاسی':'شماره شاسی', 'شماره موتور':'شماره موتور',
    'نقل و انتقاالت':'نقل و انتقالات', 'انتقاالت':'انتقالات',
    'آییننامه':'آیین‌نامه', 'آیین نامه':'آیین‌نامه',
    'قوانینومقررات':'قوانین و مقررات', 'قوهقضائیه':'قوه قضائیه',
    'دادخواستهای':'دادخواست‌های', 'دادخواستها':'دادخواست‌ها',
    'وکالتنامه':'وکالت‌نامه', 'وکالتنامههای':'وکالت‌نامه‌های',
    'مبالغ مذکور':'مبالغ مذکور',
    'مشقتبار':'مشقت‌بار', 'مشقت بار':'مشقت‌بار',
    'هزینههای':'هزینه‌های', 'هزینهها':'هزینه‌ها',
    'هزینههای قانونی':'هزینه‌های قانونی', 'چهارماه':'چهار ماه',
    'سالهای':'سال‌های', 'هزینههایشان':'هزینه‌هایشان',
}


def _load_spacing_lexicon():
    try:
        with open(SPACING_LEXICON_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("joined_to_canonical", {}) if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}

SPACING_LEXICON = _load_spacing_lexicon()

# Compile one bounded OCR/spacing matcher instead of compiling and executing
# dozens of regular expressions for every corpus record.  This is equivalent
# in intent to the old token-bounded replacements, but dramatically reduces
# corpus-load CPU cost.
_REPAIR_MAP = {}
_REPAIR_MAP.update(SPACING_LEXICON)
_REPAIR_MAP.update(COMMON)
if _REPAIR_MAP:
    _REPAIR_KEYS = sorted(_REPAIR_MAP, key=len, reverse=True)
    _REPAIR_RE = re.compile(
        r'(?<![\u0600-\u06ff])(?:' + '|'.join(re.escape(k) for k in _REPAIR_KEYS) + r')(?![\u0600-\u06ff])'
    )
else:
    _REPAIR_RE = None

def _repair_match(match):
    return _REPAIR_MAP.get(match.group(0), match.group(0))


def cleanup_legal_text(text):
    s = str(text or '').replace('\ufeff','').replace('\u200e','').replace('\u200f','')
    s = s.replace('ي','ی').replace('ى','ی').replace('ك','ک').replace('ـ','')
    s = s.translate(str.maketrans({
        '\ufefb':'لا','\ufefc':'لا','\ufef9':'لا','\ufefa':'لا','\ufef7':'لا','\ufef8':'لا',
        '\ufef5':'لا','\ufef6':'لا'
    }))
    # Only isolated split lam-alef is safe to join; never globally swap «ال»/«لا».
    s = re.sub(r'(?<!\S)ا[\u200c\u200d ]+ل(?!\S)', 'لا', s)
    # Exact-token spacing/OCR repairs. Unknown concatenations remain intact.
    if _REPAIR_RE is not None:
        s = _REPAIR_RE.sub(_repair_match, s)
    s = re.sub(r'[ \t]+', ' ', s)
    s = re.sub(r'[ \t]*\n[ \t]*', '\n', s)
    s = re.sub(r'\s+([،؛:»؟])', r'\1', s)
    s = re.sub(r'([«(]) +', r'\1', s)
    s = re.sub(r' +([)])', r'\1', s)
    s = re.sub(r'\n{3,}', '\n\n', s)
    return s.strip()
