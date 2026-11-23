# LegalBot — P1 Patch Notes — 2026-10-08

این نسخه با احتیاط روی نسخه اصلاح‌شده قبلی اعمال شده است. هیچ جدول یا قابلیت موجودی حذف نشده است.

## P1-01 — Account / Credits / Subscription
- endpoint جدید `GET /api/v1/account`
- اطلاعات امن حساب + اعتبار باقی‌مانده + دوره اعتبار + وضعیت اشتراک را برمی‌گرداند.
- Mini App صفحه حساب را به endpoint جدید متصل می‌کند.
- اطلاعات حساس کاربر از پاسخ حذف می‌شوند.

## P1-02 — Case Tasks
- endpointهای جدید:
  - `GET /api/v1/cases/{id}/tasks`
  - `POST /api/v1/cases/{id}/tasks`
  - `PATCH /api/v1/cases/{id}/tasks/{task_id}`
  - `DELETE /api/v1/cases/{id}/tasks/{task_id}`
- تمام عملیات user-scoped هستند.
- پرونده بایگانی‌شده قابل تغییر نیست.
- Mini App برای هر پرونده صفحه «کارهای پرونده» دارد.

## P1-03 — Lawyer Note
- endpointهای جدید:
  - `GET /api/v1/cases/{id}/note`
  - `POST /api/v1/cases/{id}/note`
- ذخیره/پاک‌کردن یادداشت خصوصی وکیل.
- محدودیت ۴۰٬۰۰۰ کاراکتر در API.
- Mini App صفحه «یادداشت وکیل» دارد.

## Regression / Validation
- Python syntax: PASS
- JavaScript syntax: PASS
- Full test suite: **52 passed**
- Live HTTP smoke test: PASS
  - Account: 200
  - Create case: 201
  - Create task: 201
  - Save note: 200
  - Read tasks: 200
  - Read note: 200

## Deliberately not changed
- Core legal intelligence
- Evidence engine
- Timeline engine
- AI provider logic
- Drafting engine
- Existing Telegram handlers
- Database migrations unrelated to P1

## Remaining P1 candidates
- Full Mini App drafting review/version compare/export UI
- Authorities/source browser UI
- broader subscription/payment UI

Telegram production E2E still requires the real HTTPS Mini App + BotFather configuration and cannot be proven from this local test environment alone.
