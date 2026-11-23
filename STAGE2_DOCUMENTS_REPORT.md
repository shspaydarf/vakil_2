# LegalBot — Stage 2: Documents

## هدف
تکمیل عمودی مدیریت اسناد در Mini App بدون بازنویسی Core: انتخاب چند فایل، آپلود، اعتبارسنجی، استخراج متن، ذخیره پایدار، نمایش نتیجه و حذف سند.

## مسیر نهایی
`Mini App → HTTP API → DocumentService → storage/repository → DB`

## قابلیت‌های اضافه‌شده
- `GET /api/v1/cases/{case_id}/documents`
  - لیست metadata امن اسناد
  - تعداد نویسه استخراج‌شده و preview کوتاه
  - سقف حجم و تعداد فایل برای UI
- `POST /api/v1/cases/{case_id}/documents`
  - `multipart/form-data`
  - چند فایل در یک درخواست
  - PDF / DOCX / TXT / JPG / JPEG / PNG / WEBP
  - محدودیت حجم هر فایل بر اساس `MAX_FILE_MB`
- `DELETE /api/v1/cases/{case_id}/documents/{document_id}`
  - حذف ثبت DB و فایل durable مربوطه
- `DocumentService.add_files()`
  - یکپارچه‌سازی upload batch
  - اولین upload برای پرونده خالی، پرونده را به وضعیت completed می‌رساند
  - uploadهای بعدی به‌عنوان addition session ثبت می‌شوند
  - سقف addition و تعداد فایل رعایت می‌شود
  - important dates بعد از ingest استخراج و ثبت می‌شوند
- `DocumentService.public_list()`
  - جلوگیری از ارسال مستقیم `extracted_text` کامل در قرارداد API/workspace
- Workspace اکنون metadata امن اسناد را در قرارداد Product دریافت می‌کند.
- Mini App:
  - پنل اسناد داخل Workspace
  - افزودن چند فایل هم‌زمان
  - نمایش queue فایل‌ها
  - وضعیت/متادیتا/preview متن
  - preview سند
  - حذف سند با تأیید
  - loading / empty / error / retry states

## Hardening
- parser چندبخشی بدون وابستگی `cgi`؛ سازگار با Python 3.13
- پاک‌سازی فایل temporary بعد از request
- حذف فایل durable هنگام حذف سند
- جلوگیری از دسترسی cross-user از طریق سرویس/Repository
- archived case قابل ویرایش نیست

## Validation
- `pytest -q --ignore=tests/test_ai_entitlement.py` → **29 passed**
- Stage 2 document/core/API tests → **21 passed**
- `preflight.py` → **PASS**
- Python compile → **PASS**
- `node --check miniapp/app.js` → **PASS**
- HTTP live document smoke → **PASS**
  - GET empty list
  - multipart upload
  - document extraction/registration
  - GET metadata
  - DELETE document + durable storage cleanup

## Known baseline issue
`tests/test_ai_entitlement.py::test_ai_free_user_reserve_commit_refund` در snapshot فعلی مستقل از تغییرات Stage 2 fail می‌شود؛ در اجرای جداگانه نیز fail است و به مسیر Documents مربوط نیست. این مورد عمداً در Stage 2 دستکاری نشد.

## فایل‌های اصلی تغییرکرده
- `legal_bot/core/documents.py`
- `legal_bot/core/product.py`
- `legal_bot/api.py`
- `miniapp/app.js`
- `miniapp/styles.css`
- `tests/test_document_service.py`

## مرحله بعد
Stage 3: Evidence + Timeline — تبدیل اسناد ثبت‌شده به زنجیره قابل بررسیِ «سند → ادعا/شاهد → رویداد → تعارض» داخل Workspace.
