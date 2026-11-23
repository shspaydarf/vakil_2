import json
from pathlib import Path
from .config import DATA_DIR
import hashlib
from threading import Lock

ROOT = Path(DATA_DIR) / 'iran'
REGISTRY = {}
AUTHORITY_BY_ID = {}
LAW_BY_TITLE = {}
_loaded = False
_load_lock = Lock()


def _ensure_loaded():
    """Load the source registry on first legal-source lookup, not API import."""
    global _loaded
    if _loaded:
        return
    with _load_lock:
        if _loaded:
            return
        with open(ROOT / 'official_sources.json', encoding='utf-8') as source:
            registry = json.load(source)
        if not isinstance(registry, dict):
            raise ValueError('Official source registry must contain a JSON object')
        authorities = {item['id']: item for item in registry.get('authorities', []) if isinstance(item, dict) and item.get('id')}
        laws = {item['title']: item for item in registry.get('laws', []) if isinstance(item, dict) and item.get('title')}
        REGISTRY.clear()
        REGISTRY.update(registry)
        AUTHORITY_BY_ID.clear()
        AUTHORITY_BY_ID.update(authorities)
        LAW_BY_TITLE.clear()
        LAW_BY_TITLE.update(laws)
        _loaded = True


def law_source(title):
    _ensure_loaded()
    item = LAW_BY_TITLE.get(title, {})
    urls = item.get('known_source_urls') or []
    authority_ids = item.get('primary_sources') or []
    return {
        'title': title,
        'status': item.get('status', 'source_pending_import'),
        'priority': item.get('priority'),
        'article_range': item.get('article_range'),
        'known_source_urls': urls,
        'primary_sources': [AUTHORITY_BY_ID[x]['name'] for x in authority_ids if x in AUTHORITY_BY_ID],
        'primary_source_ids': [x for x in authority_ids if x in AUTHORITY_BY_ID],
        'last_verified': item.get('last_verified'),
        'cross_check_urls': item.get('cross_check_urls') or [],
        'activation_note': item.get('activation_note'),
    }


def is_text_verified(title):
    _ensure_loaded()
    status = LAW_BY_TITLE.get(title, {}).get('status', '')
    return status in {'verified', 'verified_current', 'verified_current_source_backed'}


def verification_label(title):
    _ensure_loaded()
    status = LAW_BY_TITLE.get(title, {}).get('status', '')
    if status in {'verified_current_source_backed'}:
        return 'متن جاری بر پایه منبع رسمی ثبت‌شده؛ آخرین تطبیق در پرونده منبع درج شده'
    if status in {'verified', 'verified_current'}:
        return 'منبع و متن تأییدشده'
    if status == 'user_pdf_active':
        return 'متن فعال از PDF ارسالی؛ آخرین اصلاحات رسمی هنوز مستقل تطبیق نشده'
    if status == 'user_pdf_historical':
        return 'متن تاریخی/نسخه قدیمی؛ برای استناد به متن جاری استفاده نشود مگر با تطبیق نسخه جدید'
    if status == 'source_verified_text_pending':
        return 'منبع رسمی شناسایی شده؛ متن محلی هنوز تأیید نشده'
    if status == 'bundled_text_unverified':
        return 'متن محلی هنوز از نظر منبع/اعتبار نهایی تأیید نشده'
    return 'منبع در صف ورود و تطبیق'


def citation_for_record(record):
    """Build a stable, human-auditable citation envelope without inventing authority."""
    record = record if isinstance(record, dict) else {}
    kind = str(record.get('kind') or 'law')
    title = str(record.get('title') or record.get('law') or '').strip()
    number = str(record.get('article') or record.get('ruling_number') or record.get('consultation_number') or '').strip()
    status = str(record.get('source_status') or '').strip()
    urls = list(record.get('source_urls') or [])
    authorities = list(record.get('primary_sources') or [])
    source_file = record.get('source_file')
    raw_key = '|'.join([kind, title, number, status, str(urls), str(source_file)])
    cid = 'CIT-' + hashlib.sha256(raw_key.encode('utf-8')).hexdigest()[:12].upper()
    return {
        'id': cid,
        'kind': kind,
        'title': title,
        'locator': number,
        'status': status or 'unknown',
        'verification_label': record.get('verification_label') or 'وضعیت منبع نامشخص',
        'primary_sources': authorities,
        'source_urls': urls,
        'cross_check_urls': list(record.get('cross_check_urls') or []),
        'last_verified': record.get('last_verified'),
        'source_file': source_file,
        'activation_note': record.get('activation_note'),
    }
