# مرحله ۱.۳ — اتصال Connector به Source Registry و Document Catalog

## دامنه

این مرحله یک مسیر اجرایی آفلاین برای پردازش HTML از قبل ذخیره‌شده/تأمین‌شده می‌سازد. این قابلیت crawler، درخواست شبکه، دانلود PDF یا ورود به بانک فعال نیست.

## تغییرات

- `connector_catalog_ingestor.py` افزوده شد تا Connector، رجیستری منبع، مبدل مرحله ۱.۲، کاتالوگ و checkpoint را به هم متصل کند.
- شناسه منبع Connector باید در Source Registry ثبت شده باشد.
- میزبان صفحهٔ کشف و همه URLهای صفحه/دارایی/سند باید هم‌زمان با allowlist خود Connector و host/root رجیستری تطبیق داشته باشند.
- نوع سند خروجی باید در صورت تعریف محدودیت نوع سند در رجیستری مجاز باشد.
- ثبت تکراری با هویت پایدار کاتالوگ idempotent است.
- منبع secondary یا unverified می‌تواند در کاتالوگ ثبت شود اما وضعیت آن quarantine باقی می‌ماند.
- `SourceRecord.recognizes_url` برای اعتبارسنجی منشأ URL بدون اعطای مجوز شبکه افزوده شد.
- `permits_url` همچنان فقط برای منبع verified با access_mode برابر polite_public_read مجوز می‌دهد.
- `DocumentCatalog` برای ثبت فراداده از `recognizes_url` استفاده می‌کند؛ دریافت شبکه همچنان باید جداگانه `permits_url` را کنترل کند.

## ایمنی

- network calls: صفر
- downloads: صفر
- active legal bank writes: صفر
- authority upgrade: انجام نمی‌شود
- unverified/secondary: قرنطینه

## محدودیت‌ها

- آزمون‌ها با HTML fixture و منبع آزمایشی انجام می‌شوند.
- اتصال زنده به سایت‌ها و robots.txt در این مرحله آزموده نشده است.
- مرحله بعد باید مسیر کاتالوگ تا صف دانلود را با کنترل مجوز شبکه تکمیل کند.
