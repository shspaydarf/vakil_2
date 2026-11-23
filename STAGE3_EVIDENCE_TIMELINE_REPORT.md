# LegalBot Stage 3 — Evidence + Timeline

## هدف
تکمیل لایه‌ی Evidence و Timeline در Mini App بدون انتقال منطق حقوقی به UI.

## تغییرات
- API مستقل برای `GET /api/v1/cases/{id}/timeline`
- API مستقل برای `GET /api/v1/cases/{id}/evidence`
- فیلتر Timeline بر اساس تاریخ‌دار/بدون‌تاریخ و status/type
- فیلتر Evidence بر اساس وضعیت claim
- نمایش Timeline با provenance سند، صفحه و محل متن
- نمایش Evidence Matrix با claim status، منبع مستقل و شواهد مخالف/پشتیبان
- هشدار تعارض زمانی و evidence gap در UI
- حفظ مرز بررسی انسانی؛ Timeline/Evidence نتیجه قطعی حقوقی تولید نمی‌کنند

## Core hardening
Issue Map اکنون `document_id` را همراه signal نگه می‌دارد. این اصلاح برای تشخیص «منبع مستقل» در Evidence ضروری بود؛ بدون آن دو سند متفاوت ممکن بود به‌اشتباه یک منبع تلقی شوند.

## معماری
`Mini App → HTTP API → Product/Core → Timeline Engine / Evidence Engine → Repository / DB`

UI فقط نمایش و فیلتر را انجام می‌دهد؛ extraction، provenance، deduplication، conflict detection و evidence status در Core باقی مانده‌اند.

## Validation
- Full pytest: **33 passed**
- Preflight: **PASS**
- Python compile: **PASS**
- JavaScript syntax: **PASS**
- HTTP smoke: **PASS**
  - `/healthz`
  - cases list
  - workspace
  - timeline
  - evidence
- Import smoke در محیط تمیز: **PASS**

## نکته
یک dependency جاافتاده‌ی `persian_case_search.py` که در artifact ارسالی موجود نبود، از baseline audited Stage 2 وارد بسته نهایی شد تا import کامل API/Core در محیط تمیز تضمین شود.
