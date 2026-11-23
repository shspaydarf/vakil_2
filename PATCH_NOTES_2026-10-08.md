# LegalBot — اصلاحات نسخه 2026-10-08

## اصلاحات انجام‌شده

### P0 — Telegram Mini App authentication
- Telegram WebApp SDK به `miniapp/index.html` اضافه شد و قبل از `app.js` لود می‌شود.
- CSP برای اجازه بارگذاری SDK رسمی Telegram از `https://telegram.org` اصلاح شد.
- مسیر موجود `X-Telegram-Init-Data` در Frontend اکنون می‌تواند از SDK واقعی Telegram مقدار بگیرد.
- Backend همچنان اعتبارسنجی HMAC و تاریخ `initData` را انجام می‌دهد و احراز هویت توسعه‌ای فقط در صورت فعال‌سازی صریح قابل استفاده است.

### P1 — Account / Settings
- دکمه تنظیمات و تب «حساب» دیگر placeholder نیستند.
- Mini App به `GET /api/v1/me` متصل شد.
- اطلاعات غیرحساس کاربر و نسخه API در پنجره حساب نمایش داده می‌شود.
- در حالت Demo نیز مسیر حساب رفتار مشخص دارد.

### Bug fix — وضعیت Timeline
- در `miniapp/app.js` تابع `statusLabel` دوبار تعریف شده بود و تعریف دوم، mapping وضعیت‌های Timeline را overwrite می‌کرد.
- این دو formatter به `timelineStatusLabel` و `caseStatusLabel` تفکیک شدند.

### Regression tests
سه تست جدید برای جلوگیری از برگشت این مشکلات اضافه شد:
- وجود و ترتیب صحیح Telegram WebApp SDK و CSP
- یکتا بودن formatterهای وضعیت
- اتصال Account به `/api/v1/me`

## تست‌های اجراشده

- `pytest -q` → **51 passed**
- `node --check miniapp/app.js` → **PASS**
- `python -m py_compile legal_bot/*.py legal_bot/core/*.py legal_bot/repositories/*.py` → **PASS**

## محدودیت باقی‌مانده

تست واقعی داخل کلاینت Telegram با BotFather/دامنه HTTPS و `BOT_TOKEN` واقعی در این محیط قابل انجام نیست. بنابراین قبل از انتشار نهایی باید یک تست acceptance داخل Telegram انجام شود:

`Telegram → Mini App → initData → API → /me → cases → workspace`
