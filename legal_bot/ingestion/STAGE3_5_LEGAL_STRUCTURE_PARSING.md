# مرحله ۳.۵ — تشخیص ساختار حقوقی اسناد

## هدف
تبدیل خروجی متنی مرحله ۳.۳ یا خروجی OCR مرحله ۳.۴ به یک ساختار میانی قابل بازبینی؛ بدون ورود خودکار به بانک JSON فعال.

## ماژول
`legal_bot.ingestion.legal_structure_parser`

توابع اصلی:
- `parse_legal_structure(pages, source_sha256="", document_type="unknown")`
- `write_legal_structure_json(result, output_path)`

ورودی `pages` همان آرایه صفحه‌محور مراحل قبل است؛ هر عضو دست‌کم `page_number` و `text` دارد. بنابراین خروجی استخراج متن و OCR هر دو قابل استفاده‌اند.

## اجزای شناسایی‌شده
- عنوان احتمالی سند
- مرجع/صادرکننده احتمالی
- تاریخ‌های دارای برچسب تاریخ تصویب/ابلاغ
- متن مقدماتی پیش از ماده نخست
- مواد و شماره ماده
- تبصره‌های شماره‌دار یا بدون شماره
- بندهای دارای شناسه حرفی یا عددی
- اجزای شماره‌دار زیر بند، در مواردی که الگو قابل تشخیص باشد
- متن انتهایی پس از آخرین ماده، در صورت وجود

تمام خطوط ساختاریافته، شماره صفحه و شماره خط منبع را حفظ می‌کنند. شماره صفحات در ورودی/خروجی همان شماره صفحه مرحله قبل است.

## محدودیت‌ها و ایمنی
- این parser مبتنی بر الگوهای قطعی و محافظه‌کارانه است؛ فهم معنایی یا تفسیر حقوقی انجام نمی‌دهد.
- تشخیص عنوان، مرجع و تاریخ احتمالی است و ممکن است در اسناد غیرمعمول اشتباه کند.
- چیدمان چندستونی، جداول، پاورقی‌ها، مواد اصلاحی و شماره‌گذاری‌های خاص ممکن است نیازمند قواعد تکمیلی باشند.
- خروجی همیشه `review_required=true` دارد و برای استفاده حقوقی باید با PDF اصلی مقابله شود.
- JSON ساختاریافته فقط sidecar مرحله‌ای است؛ هیچ مسیر نوشتنی به بانک فعال قوانین ندارد.
- برای صفحات OCR، منشأ OCR باید از ورودی مرحله ۳.۴ و manifest مربوط نگهداری شود؛ parser متن را به‌تنهایی به‌عنوان متن قطعی تأیید نمی‌کند.

## نمونه استفاده
```python
from legal_bot.ingestion.pdf_text_extractor import extract_pdf_text
from legal_bot.ingestion.legal_structure_parser import parse_legal_structure, write_legal_structure_json

extracted = extract_pdf_text("document.pdf")
structured = parse_legal_structure(
    extracted.pages,
    source_sha256=extracted.source_sha256,
    document_type="law",
)
write_legal_structure_json(structured, "staging/document.structure.json")
```

برای OCR نیز می‌توان `ocr_result.pages` را به `parse_legal_structure` داد.

## آزمون‌ها
آزمون‌ها شامل تشخیص عنوان/مرجع/تاریخ، مواد، تبصره، بند، حفظ صفحه و خط منبع، شماره ماده تکراری، ورودی خالی و نوشتن اتمیک sidecar هستند.
