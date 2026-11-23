# گزارش مرحله ۱.۳ — اتصال Connectorها به Source Registry و Document Catalog

## نتیجه

مسیر آفلاین و قابل آزمون برای عبور HTML از پیش تأمین‌شده از Connector، سیاست منبع، مبدل مرحله ۱.۲، کاتالوگ و checkpoint اضافه شد.

## تغییرات کد

- افزوده‌شدن `legal_bot/ingestion/connector_catalog_ingestor.py` با کلاس `ConnectorCatalogIngestor` و متد `ingest_saved_html`.
- کنترل ثبت منبع در `SourceRegistry` پیش از پردازش.
- کنترل هم‌پوشانی دقیق host بین تعریف Connector و رجیستری.
- کنترل HTTPS، host و canonical root برای صفحهٔ کشف، صفحهٔ سند و asset URL.
- کنترل نوع سند کاتالوگ در برابر `document_types` رجیستری، در صورت تعریف محدودیت.
- استفاده از `candidate_adapter` و `DiscoveryMemoryBridge` برای ثبت کاتالوگی و checkpoint.
- retry همان شناسهٔ پایدار، سند تکراری جدید ایجاد نمی‌کند.
- اعتبارسنجی URL در `DocumentCatalog` برای هر سه فیلد `document_url`، `discovery_page_url` و `asset_url` تکمیل شد.
- `SourceRecord.recognizes_url()` از `permits_url()` جدا شد: اولی فقط منشأ URL را برای ثبت metadata بررسی می‌کند؛ دومی علاوه بر آن وضعیت verified و `polite_public_read` را برای اجازهٔ شبکه الزام می‌کند.

## آزمون‌ها

- آزمون‌های جدید اتصال Connector به کاتالوگ: ۷ مورد.
- آزمون کامل پروژه: **۸۷۳ موفق، صفر ناموفق**.
- `compileall`: موفق.
- CRC آرشیو نهایی: باید پس از بسته‌بندی بررسی شود.
- هش چهار بانک فعال مطابق خط مبنا و بدون تغییر:
  - laws.json: `d21b1c56a575511973836271a54d98286a06aff07e93e7852abd0cd1f3f4e7f6`
  - rulings.json: `2ff2845a9d8f9da61abb1d695684335e8fb68bdd52783ebbde1148225bbc3236`
  - consultations.json: `30bcac47ebeb98a7c8f14b3c35cbb16ce50454ed3853ca92eb47ff4ee827a7a9`
  - samples_and_circulars.json: `2b042cacf719e2148acf27f317e8233fc0950b4fb99754cccc9bef236b2ba748`

## مرزهای این مرحله

- HTML از fixture یا ورودی ذخیره‌شده پردازش می‌شود؛ هیچ درخواست شبکه‌ای انجام نشده است.
- PDF دانلود نشده است.
- دسترسی زنده، robots.txt و نرخ درخواست منبع واقعی بررسی نشده است.
- هیچ رکوردی به بانک حقوقی فعال نوشته نشده است.
- منبع unverified یا secondary در کاتالوگ قابل ثبت است، اما در quarantine باقی می‌ماند و به pipeline رسمی ارتقا نمی‌یابد.

## مرحلهٔ بعد

اتصال کاتالوگ به Download Queue با کنترل مستقل `SourceRecord.permits_url()`، محدودیت میزبان و جلوگیری از صف‌بندی URL غیرمجاز.
