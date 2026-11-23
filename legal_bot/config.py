import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / 'data'
LAW_FILE = DATA_DIR / 'iran' / 'laws.json'
GLOSSARY_FILE = DATA_DIR / 'iran' / 'legal_glossary.json'
UPLOAD_DIR = BASE_DIR / 'uploads'
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
# V67: durable case files live outside the temporary upload directory.
STORAGE_DIR = Path(os.getenv('LEGALBOT_STORAGE_DIR', str(BASE_DIR / 'storage')))
CASE_STORAGE_DIR = STORAGE_DIR / 'cases'
TEMP_STORAGE_DIR = STORAGE_DIR / 'temp'
BACKUP_DIR = Path(os.getenv('LEGALBOT_BACKUP_DIR', str(BASE_DIR.parent / 'legal_bot_backups')))
TEMP_FILE_RETENTION_HOURS = max(1, int(os.getenv('TEMP_FILE_RETENTION_HOURS','24')))
AI_HISTORY_RETENTION_DAYS = max(1, int(os.getenv('AI_HISTORY_RETENTION_DAYS','180')))
DONE_TASK_RETENTION_DAYS = max(1, int(os.getenv('DONE_TASK_RETENTION_DAYS','180')))
FEEDBACK_RETENTION_DAYS = max(1, int(os.getenv('FEEDBACK_RETENTION_DAYS','180')))
REMINDER_RETENTION_DAYS = max(1, int(os.getenv('REMINDER_RETENTION_DAYS','180')))
QUOTA_RETENTION_MONTHS = max(1, int(os.getenv('QUOTA_RETENTION_MONTHS','13')))
DELETED_LISTING_RETENTION_DAYS = max(1, int(os.getenv('DELETED_LISTING_RETENTION_DAYS','30')))
REFERRAL_RETENTION_DAYS = max(1, int(os.getenv('REFERRAL_RETENTION_DAYS','180')))
LICENSE_REFERENCE_RETENTION_DAYS = max(1, int(os.getenv('LICENSE_REFERENCE_RETENTION_DAYS','30')))
LOG_RETENTION_DAYS = max(1, int(os.getenv('LOG_RETENTION_DAYS','90')))
DAILY_BACKUPS = max(1, int(os.getenv('DAILY_BACKUPS','14')))
WEEKLY_BACKUPS = max(1, int(os.getenv('WEEKLY_BACKUPS','8')))
MONTHLY_BACKUPS = max(1, int(os.getenv('MONTHLY_BACKUPS','3')))
BACKUP_INTERVAL_HOURS = max(1, int(os.getenv('BACKUP_INTERVAL_HOURS','24')))
STORAGE_DIR.mkdir(parents=True, exist_ok=True)
CASE_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
TEMP_STORAGE_DIR.mkdir(parents=True, exist_ok=True)


BOT_TOKEN = os.getenv('BOT_TOKEN', '').strip()
MINIAPP_URL = os.getenv('MINIAPP_URL', '').strip().rstrip('/')
ADMIN_TELEGRAM_IDS = {int(x.strip()) for x in os.getenv('ADMIN_TELEGRAM_IDS','').split(',') if x.strip().lstrip('-').isdigit()}
PHONE_HASH_SECRET = os.getenv('PHONE_HASH_SECRET','').strip()
# Never fall back to a known/shared secret. Production startup validation is
# performed in main.py; tests can provide an explicit value.
PHONE_HASH_SECRET_MIN_LEN = max(32, int(os.getenv('PHONE_HASH_SECRET_MIN_LEN','32')))
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY','').strip()
AI_ENABLED = os.getenv('AI_ENABLED','1').lower() in {'1','true','yes','on'}
# Legal documents can contain privileged/confidential information. External
# model processing is opt-in rather than implicit.
AI_EXTERNAL_DATA_CONSENT = os.getenv('AI_EXTERNAL_DATA_CONSENT','0').lower() in {'1','true','yes','on'}
AI_MAX_CHARS = max(20000, int(os.getenv('AI_MAX_CHARS','180000')))
AI_TEXT_MAX_CHARS = max(1000, int(os.getenv('AI_TEXT_MAX_CHARS','12000')))
AI_MONTHLY_TEXT_LIMIT = max(0, int(os.getenv('AI_MONTHLY_TEXT_LIMIT','30')))
AI_CASE_MONTHLY_LIMIT = max(0, int(os.getenv('AI_CASE_MONTHLY_LIMIT','5')))
SUBSCRIPTION_AI_MONTHLY_LIMIT = max(0, int(os.getenv('SUBSCRIPTION_AI_MONTHLY_LIMIT','100')))
# Local-first policy: case analysis never calls an external model automatically.
AI_CASE_AUTO = os.getenv('AI_CASE_AUTO','0').lower() in {'1','true','yes','on'}
AI_DEEP_ON_DEMAND = os.getenv('AI_DEEP_ON_DEMAND','1').lower() in {'1','true','yes','on'}
CASE_TEXT_RETENTION = max(0, int(os.getenv('CASE_TEXT_RETENTION','1')))
AI_BASE_URL = os.getenv('AI_BASE_URL','https://api.deepseek.com').rstrip('/')
AI_MODEL = os.getenv('AI_MODEL','deepseek-chat').strip() or 'deepseek-chat'
AI_VISION_ENABLED = os.getenv('AI_VISION_ENABLED','0').lower() in {'1','true','yes','on'}
AI_VISION_MODEL = os.getenv('AI_VISION_MODEL','').strip()
AI_RECOVERY_MAX_PAGES = max(1, min(5, int(os.getenv('AI_RECOVERY_MAX_PAGES','3'))))
FEEDBACK_ENABLED = os.getenv('FEEDBACK_ENABLED','1').lower() in {'1','true','yes','on'}
SUPPORT_EMAIL = os.getenv('SUPPORT_EMAIL','').strip()
ADMIN_CARD_NUMBER = os.getenv('ADMIN_CARD_NUMBER','').strip()
ADMIN_CARD_HOLDER = os.getenv('ADMIN_CARD_HOLDER','').strip()
SUBSCRIPTION_PRICE_TEXT = os.getenv('SUBSCRIPTION_PRICE_TEXT','اشتراک یک‌ماهه').strip()
FREE_CASES = int(os.getenv('FREE_CASES','3'))

# V195: unified free credit system. Values are intentionally configurable so
# pricing/cost calibration can change without changing business logic.
FREE_WEEKLY_CREDITS = max(1, int(os.getenv('FREE_WEEKLY_CREDITS', '250')))
CREDIT_CASE_COST = max(1, int(os.getenv('CREDIT_CASE_COST', '10')))
CREDIT_AI_QUESTION_COST = max(1, int(os.getenv('CREDIT_AI_QUESTION_COST', '30')))
MAX_FILE_MB = max(1, min(int(os.getenv('MAX_FILE_MB','20')), 20))
# Aggregate HTTP upload limit protects the API from buffering an unbounded
# multi-file multipart body in memory. Keep nginx's limit slightly above this.
MAX_UPLOAD_REQUEST_MB = max(1, min(int(os.getenv('MAX_UPLOAD_REQUEST_MB', '25')), 64))
MAX_TEXT_CHARS = max(1000, min(int(os.getenv('MAX_TEXT_CHARS','1000000')), 2_000_000))
MAX_DOCUMENT_PAGES = max(1, min(int(os.getenv('MAX_DOCUMENT_PAGES', '250')), 500))
MAX_ALBUM_IMAGES = int(os.getenv('MAX_ALBUM_IMAGES','20'))
CASE_NAME_MAX_CHARS = max(20, min(120, int(os.getenv('CASE_NAME_MAX_CHARS','80'))))
MAX_CASE_VERSIONS = max(0, min(5, int(os.getenv('MAX_CASE_VERSIONS','5'))))
MAX_CASE_ADDITIONS = max(0, min(10, int(os.getenv('MAX_CASE_ADDITIONS','8'))))
MAX_CASE_ADDITION_FILES = max(1, min(MAX_ALBUM_IMAGES, int(os.getenv('MAX_CASE_ADDITION_FILES', str(MAX_ALBUM_IMAGES)))))
MAX_CASE_UPLOAD_FILES = max(1, min(MAX_ALBUM_IMAGES, int(os.getenv('MAX_CASE_UPLOAD_FILES', '12'))))
# Lawyer note limit: roughly 10 Persian text pages at ~2,000 chars/page.
MAX_CASE_NOTE_CHARS = max(1000, min(20000, int(os.getenv('MAX_CASE_NOTE_CHARS','20000'))))
OCR_ENABLED = os.getenv('OCR_ENABLED','1').lower() in {'1','true','yes','on'}
DEBUG_EXTRACTION = os.getenv('DEBUG_EXTRACTION','0').lower() in {'1','true','yes','on'}
TESSERACT_CMD = os.getenv('TESSERACT_CMD','').strip()
TESSERACT_LANG = os.getenv('TESSERACT_LANG','fas+eng').strip() or 'eng'
DB_PATH = Path(os.getenv('LEGALBOT_DB_PATH', str(BASE_DIR / 'legal_bot.db')))

SUBSCRIPTION_CARD = os.getenv("SUBSCRIPTION_CARD", "شماره کارت را در Secrets ریپلیت وارد کنید")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS","").split(",") if x.strip().isdigit()]

FREE_PROMO_CHANNEL_ID = os.getenv("FREE_PROMO_CHANNEL_ID","")

FREE_PROMO_CHANNEL_USERNAME = os.getenv("FREE_PROMO_CHANNEL_USERNAME","")

FREE_PROMO_CHANNEL_TITLE = os.getenv("FREE_PROMO_CHANNEL_TITLE","کانال تبلیغاتی ماه")

FREE_INFO_CHANNEL_ID = os.getenv("FREE_INFO_CHANNEL_ID","")

FREE_INFO_CHANNEL_USERNAME = os.getenv("FREE_INFO_CHANNEL_USERNAME","")

FREE_INFO_CHANNEL_TITLE = os.getenv("FREE_INFO_CHANNEL_TITLE","آموزش و اطلاع‌رسانی")

# Registration is intentionally relaxed for the launch phase. The lawyer-code
# field and verification logic remain in the database/code, but the code is not
# required while this flag is false.
REQUIRE_LAWYER_VERIFICATION = os.getenv('REQUIRE_LAWYER_VERIFICATION','0').lower() in {'1','true','yes','on'}
