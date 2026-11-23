# MACHINA — پاکسازی کم‌خطر Batch 3

تاریخ: 2026-10-31
مبنای کار: خروجی ممیزی Batch 2، مبتنی بر ZIP مرحله 5.7 و بهینه‌سازی Batch 1.

## دامنه تغییر

فقط ۱۹ نام import که در تحلیل AST هیچ ارجاع اجرایی نداشتند حذف شدند. هیچ تابع، کلاس، مسیر API، handler، callback، فایل داده حقوقی، schema یا قابلیت محصول حذف یا بازنویسی نشد.

فایل‌های تغییرکرده:

1. `persian_case_search.py` — `Optional`
2. `legal_bot/api.py` — `io`
3. `legal_bot/unified_search.py` — `Iterable`
4. `legal_bot/analysis.py` — `Counter`
5. `legal_bot/db.py` — `hmac`
6. `legal_bot/backup.py` — `shutil`
7. `legal_bot/adversarial_review.py` — `List`
8. `legal_bot/property_tree.py` — `re`
9. `legal_bot/timeline_engine.py` — `Iterable`
10. `legal_bot/output_engine.py` — `List`
11. `legal_bot/calculators.py` — `dataclass`
12. `legal_bot/citation_verifier.py` — `List`
13. `legal_bot/source_json_normalizer.py` — `re`
14. `legal_bot/files.py` — `math`
15. `legal_bot/brief_workspace.py` — `Dict`
16. `legal_bot/brief_writer.py` — `Optional`
17. `legal_bot/source_segmentation.py` — `List`
18. `legal_bot/ai_usage.py` — `Path`
19. `legal_bot/repositories/cases.py` — import محلی `re` در متد `text()`

## موارد عمداً دست‌نخورده

- هیچ‌یک از ۸۱ تابع مشکوک حذف نشد؛ بسیاری ممکن است از طریق registry، route، callback یا فراخوانی پویا استفاده شوند.
- هیچ helper مشابهی ادغام نشد؛ شباهت ساختاری به‌تنهایی اثبات یکسانی رفتار نیست.
- داده‌های حقوقی و فایل‌های مفقود ساخته یا جایگزین نشدند.

## اعتبارسنجی

- `python -m compileall -q .`: موفق.
- مجموعه تست هدفمند شامل ۶۰ تست: ۵۱ موفق، ۹ ناموفق.
- همان مجموعه دقیقاً روی نسخه مبنا نیز اجرا شد و نتیجه دقیقاً یکسان بود: ۵۱ موفق، ۹ ناموفق. بنابراین تغییرات این Batch هیچ regression قابل مشاهده‌ای در این مجموعه ایجاد نکردند.
- از ۹ شکست، ۸ مورد در هر دو نسخه به نبود `legal_bot/data/iran/laws.json` هنگام import کردن API مربوط بود.
- یک تست استناد در هر دو نسخه شکست خورد: انتظار داشت عنوان «قانون مدنی» از registry استخراج شود، اما مقدار `law_title` برابر `None` بود. این مورد پیش از پاکسازی نیز وجود داشت.
- اجرای کامل pytest نیز در مرحله collection به علت همان فایل مفقود `laws.json` متوقف می‌شود.

## جمع‌بندی

این Batch صرفاً پاکسازی importهای بلااستفاده با ریسک پایین است. رفتار برنامه عمداً تغییر داده نشده است. نتیجه تست‌ها به‌صورت مقایسه‌ای با نسخه مبنا ثبت شده و نباید به‌عنوان تأیید کامل پروژه یا آمادگی production تعبیر شود.
