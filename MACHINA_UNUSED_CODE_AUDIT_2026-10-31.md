# MACHINA — ممیزی کدهای بلااستفاده و تکراری

**مبنای بررسی:** ZIP مرحله Optimization Batch 1 (نسخه ۳۱ اکتبر ۲۰۲۶)  
**فایل‌های Python تحلیل‌شده:** 175  
**تغییر کد اجرایی در این مرحله:** صفر؛ این بسته فقط گزارش ممیزی است.

## نتیجه اسکن ایستا

| دسته | تعداد نامزد |
|---|---:|
| importهای بدون ارجاع مستقیم در همان فایل (غیرتستی، بدون `__init__.py`) | 75 |
| توابع سطح ماژول با ارجاع نامی/ویژگی صفر (غیرتستی) | 81 |
| گروه‌های توابع با ساختار AST یکسان | 8 |

این اعداد **موارد قطعی قابل حذف نیستند**؛ صرفاً فهرست نامزدهای بررسی دستی‌اند.

## نکته مهم درباره false positive

- `api.py` و `handlers.py` از routeها، callbackها، registration و dispatch پویا استفاده می‌کنند. اسکن ایستا ممکن است مواردی را که با نام رشته‌ای یا registry فراخوانی می‌شوند، بلااستفاده تشخیص دهد.
- importهای `__init__.py` ممکن است API عمومی پکیج را export کنند و عمداً در همان فایل مصرف نشوند؛ از شمارش نامزدها کنار گذاشته شدند.
- توابع تستی، fixtureها و setup/teardownهای pytest از فهرست توابع کنار گذاشته شدند.
- توابع خصوصی که فقط با `getattr`، دیکشنری callback یا decorator فراخوانی شوند، ممکن است در این گزارش نامزد حذف دیده شوند.
- شباهت AST الزاماً به معنی یکسان بودن رفتار نیست؛ ممکن است قواعد پاک‌سازی یا اعتبارسنجی هر ماژول عمداً تفاوت داشته باشند.

## ۱) importهای مشکوک با اولویت بررسی

موارد زیر فقط از نظر عدم استفاده مستقیم در AST مشکوک‌اند؛ پیش از حذف باید کل فایل و استفاده‌های پویا بررسی شود:

- `persian_case_search.py:9` — `Optional` از `typing.Optional`
- `legal_bot/api.py:20` — `io` از `io`
- `legal_bot/unified_search.py:11` — `Iterable` از `typing.Iterable`
- `legal_bot/analysis.py:3` — `Counter` از `collections.Counter`
- `legal_bot/db.py:2` — `hmac` از `hmac`
- `legal_bot/backup.py:4` — `shutil` از `shutil`
- `legal_bot/adversarial_review.py:10` — `List` از `typing.List`
- `legal_bot/property_tree.py:8` — `re` از `re`
- `legal_bot/timeline_engine.py:13` — `Iterable` از `typing.Iterable`
- `legal_bot/output_engine.py:9` — `List` از `typing.List`
- `legal_bot/calculators.py:7` — `dataclass` از `dataclasses.dataclass`
- `legal_bot/citation_verifier.py:13` — `List` از `typing.List`
- `legal_bot/source_json_normalizer.py:9` — `re` از `re`
- `legal_bot/files.py:1` — `math` از `math`
- `legal_bot/brief_workspace.py:9` — `Dict` از `typing.Dict`
- `legal_bot/brief_writer.py:9` — `Optional` از `typing.Optional`
- `legal_bot/source_segmentation.py:12` — `List` از `typing.List`
- `legal_bot/ai_usage.py:9` — `Path` از `pathlib.Path`
- `legal_bot/repositories/cases.py:111` — `re` از `re`

## ۲) توابع سطح ماژول بدون ارجاع نامی/ویژگی

- `persian_case_search.py:66` — `_line_spans()`
- `legal_bot/check_assistant.py:129` — `search_hint()`
- `legal_bot/text_guard.py:201` — `needs_ai_recovery()`
- `legal_bot/drafting_artifacts.py:247` — `_work_product_is_saved()`
- `legal_bot/quiz.py:64` — `list_categories()`
- `legal_bot/quiz.py:75` — `get_questions()`
- `legal_bot/quiz.py:81` — `list_terms()`
- `legal_bot/quiz.py:108` — `format_question()`
- `legal_bot/quiz.py:117` — `format_essay()`
- `legal_bot/analysis.py:56` — `_find_all()`
- `legal_bot/analysis.py:643` — `search_cases_full_text()`
- `legal_bot/authority_engine.py:264` — `build_query_plan()`
- `legal_bot/db.py:119` — `unlink_client_case()`
- `legal_bot/db.py:215` — `has_lawyer_code()`
- `legal_bot/db.py:497` — `clear_active_case()`
- `legal_bot/db.py:574` — `get_case_version()`
- `legal_bot/db.py:614` — `grant()`
- `legal_bot/db.py:625` — `revoke()`
- `legal_bot/db.py:629` — `add_payment()`
- `legal_bot/db.py:636` — `pending_payment()`
- `legal_bot/db.py:639` — `has_pending_payment()`
- `legal_bot/db.py:642` — `approve_payment()`
- `legal_bot/db.py:648` — `reject_payment()`
- `legal_bot/db.py:902` — `reserve_ai()`
- `legal_bot/db.py:914` — `refund_ai()`
- `legal_bot/db.py:967` — `count_case_important_dates()`
- `legal_bot/db.py:1179` — `get_subscription()`
- `legal_bot/db.py:1219` — `pending_payments()`
- `legal_bot/db.py:1327` — `consume_case()`
- `legal_bot/db.py:1334` — `admin_stats()`
- `legal_bot/db.py:1353` — `admin_users()`
- `legal_bot/db.py:1397` — `admin_set_limit()`
- `legal_bot/db.py:1440` — `get_free_channel_config()`
- `legal_bot/db.py:1446` — `set_free_channels()`
- `legal_bot/db.py:1507` — `consume_free_case()`
- `legal_bot/db.py:1518` — `free_cases_available()`
- `legal_bot/db.py:1630` — `refund_ai_question()`
- `legal_bot/db.py:1647` — `ai_quota_text()`
- `legal_bot/db.py:1753` — `list_pending_service_listings()`
- `legal_bot/db.py:1855` — `list_open_referrals()`
- `legal_bot/db.py:1932` — `list_referral_events()`
- `legal_bot/db.py:2114` — `clear_drafting_workflow_session()`
- `legal_bot/laws.py:116` — `search_consultations()`
- `legal_bot/laws.py:150` — `search_rulings()`
- `legal_bot/adversarial_review.py:39` — `_maps()`
- `legal_bot/handlers.py:133` — `legal_search_menu()`
- `legal_bot/handlers.py:303` — `role_choice_keyboard()`
- `legal_bot/handlers.py:2240` — `brief_stage_keyboard()`
- `legal_bot/handlers.py:2693` — `_parse_amount()`
- `legal_bot/handlers.py:3330` — `mahr_amount_cb()`
- `legal_bot/handlers.py:3455` — `delay_amount_text()`
- `legal_bot/handlers.py:3833` — `_process_document()`
- `legal_bot/handlers.py:3886` — `format_case_version_diff()`
- `legal_bot/handlers.py:6231` — `_glossary_text()`
- `legal_bot/handlers.py:6616` — `show_ai_quota()`
- `legal_bot/handlers.py:6695` — `register_v12_choice_handlers()`
- `legal_bot/handlers.py:6720` — `v12_start_gate()`
- `legal_bot/handlers.py:6726` — `ai_question_message_router()`
- `legal_bot/handlers.py:6730` — `mark_ai_answer_success()`
- `legal_bot/handlers.py:6731` — `finalize_ai_answer()`
- `legal_bot/brief_templates.py:397` — `template_brief_type()`
- `legal_bot/calculators.py:51` — `diyah_items()`
- `legal_bot/calculators.py:118` — `parse_iso_date()`
- `legal_bot/hybrid_retrieval.py:98` — `rank_texts()`
- `legal_bot/files.py:435` — `extract()`
- `legal_bot/files.py:441` — `recovery_images()`
- `legal_bot/brief_workspace.py:33` — `history_lines()`
- `legal_bot/brief_workspace.py:102` — `diff_summary()`
- `legal_bot/brief_workspace.py:335` — `detailed_diff_summary()`
- `legal_bot/final_audit.py:7` — `run_audit()`
- `legal_bot/production.py:33` — `validate_production_config()`
- `legal_bot/formatting.py:13` — `analysis_text()`
- `legal_bot/ai.py:517` — `text_assist()`
- `legal_bot/ai.py:537` — `recover_text_from_image()`
- `legal_bot/family_assistant.py:140` — `search_hint()`
- `legal_bot/draft_engine.py:54` — `_issue_map()`
- `legal_bot/ejare_assistant.py:27` — `role_keyboard_rows()`
- `legal_bot/ejare_assistant.py:35` — `topic_keyboard_rows()`
- `legal_bot/ejare_assistant.py:169` — `search_hint()`
- `legal_bot/brief_planner.py:111` — `format_brief_plan()`
- `legal_bot/ocr_lam_alef.py:17` — `load_ocr_lexicon()`

## ۳) گروه‌های توابع با ساختار AST مشابه

- `legal_bot/contract_tree.py:12 _has()`؛ `legal_bot/ejare_tree.py:13 _has()`؛ `legal_bot/claims_tree.py:12 _has()`؛ `legal_bot/check_tree.py:14 _has()`؛ `legal_bot/property_tree.py:12 _has()`
- `legal_bot/brief_information.py:29 _clean()`؛ `legal_bot/consistency_gate.py:59 _clean()`
- `legal_bot/claims_tree.py:16 _source_hits()`؛ `legal_bot/property_tree.py:14 _source_hits()`
- `legal_bot/authority_engine.py:106 _clean()`؛ `legal_bot/rewrite_engine.py:42 _clean()`؛ `legal_bot/evidence_engine.py:18 _clean()`؛ `legal_bot/adversarial_review.py:27 _clean()`؛ `legal_bot/issue_engine.py:75 _clean()`؛ `legal_bot/timeline_engine.py:55 _clean()`؛ `legal_bot/strategy_engine.py:12 _clean()`؛ `legal_bot/draft_engine.py:23 _clean()`
- `legal_bot/calendar_dates.py:140 _pages()`؛ `legal_bot/issue_engine.py:94 _pages()`
- `legal_bot/evidence_engine.py:22 _norm()`؛ `legal_bot/issue_engine.py:79 _norm()`
- `legal_bot/core/credits.py:33 commit()`؛ `legal_bot/core/ai_entitlement.py:33 commit()`
- `legal_bot/core/ai_entitlement.py:40 question_cost()`؛ `legal_bot/repositories/entitlements.py:295 question_cost()`؛ `legal_bot/repositories/ai.py:34 question_cost()`

## پیشنهاد پاکسازی کم‌ریسک

1. ابتدا فقط importهای واضحی که هیچ اثر جانبی یا نقش export ندارند، تک‌به‌تک بررسی و حذف شوند.
2. سپس توابع خصوصی سطح ماژول بررسی شوند؛ هر مورد باید با جست‌وجوی متنی کل مخزن، routeها، callbackها، decoratorها و تست‌ها تطبیق داده شود.
3. helperهای مشابه مثل `_has` و `_clean` فعلاً ادغام نشوند. ابتدا باید تفاوت ورودی/خروجی، normalization و قواعد حقوقی هر ماژول مقایسه شود.
4. پس از هر دسته تغییر، تست‌های همان قابلیت و سپس مجموعه تست‌های گسترده اجرا شود.

**تصمیم این مرحله:** هیچ تابع یا importی به‌صورت خودکار حذف نشد تا احتمال حذف مسیرهای پویا یا قابلیت‌های قدیمیِ هنوز متصل کاهش یابد.
