# گزارش مرحله ۳.۱ — معماری موتور دریافت اسناد

تاریخ: 2026-10-31
نسخه مبنا: `MACHINA_Legal_Engine_Phase2_5_Source_Connector_Coverage_2026-10-31.zip`

## پیاده‌سازی
- صف پایدار دریافت در `legal_bot/ingestion/download_queue.py` اضافه شد.
- صف فقط CandidateDocumentهای دارای asset URL با میزبان دقیقاً مجاز را می‌پذیرد.
- جلوگیری از ثبت تکراری، محدودیت ظرفیت، ثبت وضعیت، شمارنده تلاش و زمان retry پیاده‌سازی شد.
- نوشتن فایل صف به‌صورت atomic انجام می‌شود.
- مستند معماری در `legal_bot/ingestion/STAGE3_1_DOWNLOAD_QUEUE_DESIGN.md` اضافه شد.

## مرز مرحله
این مرحله دانلود واقعی، پردازش PDF، OCR، اجرای worker زمان‌بندی‌شده یا ورود به بانک فعال را انجام نمی‌دهد. این موارد در مراحل بعدی هستند.

## آزمون
`python -m unittest discover -s tests -p 'test_*.py'`
نتیجه: ۱۴ تست موفق، صفر خطا.

## فایل‌های افزوده/تغییریافته
- افزوده: `legal_bot/ingestion/download_queue.py`
- افزوده: `legal_bot/ingestion/STAGE3_1_DOWNLOAD_QUEUE_DESIGN.md`
- افزوده: `MACHINA_LEGAL_ENGINE_PHASE3_1_REPORT_2026-10-31.md`
- تغییر: `tests/test_ingestion_architecture.py`

## وضعیت
مرحله ۳.۱ از نظر معماری صف و آزمون‌های خودکار تکمیل است. اتصال worker دانلود و آزمایش عملیاتی به مرحله ۳.۲ و بعد موکول شده است.
