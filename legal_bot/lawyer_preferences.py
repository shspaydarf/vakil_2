"""Stage 2: lawyer preference capture and review proposals (stateless).

This module deliberately does not persist profiles. Durable, owner-scoped storage
is reserved for Stage 3. Only general work preferences are accepted; case/client
facts and confidential material are explicitly out of scope.
"""
from __future__ import annotations

from copy import deepcopy


def _opts(items):
    return [{"value": value, "label": label} for value, label in items]


SCHEMA = {
    "spec_version": "1.0",
    "stage": "2_of_6",
    "persistence_enabled": False,
    "categories": [
        {
            "key": "professional_context", "title": "زمینه حرفه‌ای", "description": "اطلاعات عمومی درباره نوع فعالیت حرفه‌ای؛ بدون نام موکل یا جزئیات پرونده.",
            "fields": [
                {"key": "practice_areas", "label": "حوزه‌های فعالیت", "type": "multi_select", "options": _opts([
                    ("contracts", "قراردادها"), ("property", "املاک"), ("family", "خانواده"), ("criminal", "کیفری"),
                    ("commercial", "تجاری"), ("labor", "کار و تأمین اجتماعی"), ("administrative", "حقوق اداری"), ("other", "سایر")]), "max_items": 8},
                {"key": "jurisdiction", "label": "قلمرو حقوقی", "type": "text", "max_length": 120, "placeholder": "مثلاً: حقوق ایران"},
                {"key": "professional_role", "label": "نقش حرفه‌ای", "type": "select", "options": _opts([("lawyer", "وکیل"), ("in_house_counsel", "مشاور حقوقی سازمانی"), ("legal_researcher", "پژوهشگر حقوقی"), ("other", "سایر")])},
                {"key": "practice_context_note", "label": "توضیح عمومی فعالیت", "type": "textarea", "max_length": 300, "placeholder": "فقط توضیح عمومی؛ بدون اطلاعات موکل یا پرونده."},
            ],
        },
        {
            "key": "writing_style", "title": "سبک نگارش", "description": "لحن و میزان تفصیل متن‌هایی که MACHINA برای شما آماده می‌کند.",
            "fields": [
                {"key": "tone", "label": "لحن", "type": "select", "options": _opts([("formal", "رسمی"), ("neutral", "خنثی"), ("plain_language", "زبان ساده و روشن"), ("persuasive", "اقناعی")])},
                {"key": "detail_level", "label": "میزان تفصیل", "type": "select", "options": _opts([("concise", "مختصر"), ("balanced", "متعادل"), ("detailed", "تفصیلی")])},
                {"key": "legal_language", "label": "سطح زبان حقوقی", "type": "select", "options": _opts([("technical", "تخصصی"), ("accessible", "قابل‌فهم و ساده"), ("mixed", "ترکیبی")])},
                {"key": "preferred_language", "label": "زبان ترجیحی", "type": "select", "options": _opts([("fa", "فارسی"), ("en", "انگلیسی"), ("ar", "عربی")])},
                {"key": "style_note", "label": "توضیح تکمیلی سبک نگارش", "type": "textarea", "max_length": 500},
            ],
        },
        {
            "key": "legal_analysis", "title": "روش تحلیل حقوقی", "description": "ترتیب تحلیل و نحوه نمایش ریسک، فرض‌ها و استدلال مخالف.",
            "fields": [
                {"key": "analysis_structure", "label": "ساختار تحلیل", "type": "select", "options": _opts([("irac", "مسئله، قاعده، تطبیق، نتیجه"), ("step_by_step", "مرحله‌به‌مرحله"), ("executive_first", "نتیجه و خلاصه در ابتدا"), ("custom", "ساختار اختصاصی")])},
                {"key": "risk_focus", "label": "میزان تمرکز بر ریسک", "type": "select", "options": _opts([("low", "کم"), ("balanced", "متعادل"), ("high", "زیاد")])},
                {"key": "counterargument_review", "label": "بررسی استدلال طرف مقابل", "type": "tri_boolean"},
                {"key": "uncertainty_handling", "label": "نمایش صریح ابهام‌ها و فرض‌ها", "type": "tri_boolean"},
            ],
        },
        {
            "key": "citations_and_sources", "title": "استنادات و منابع", "description": "تراکم، قالب و اولویت منابع؛ این تنظیمات هرگز مجوز ساختن استناد نیست.",
            "fields": [
                {"key": "citation_density", "label": "میزان استناد", "type": "select", "options": _opts([("comprehensive", "جامع"), ("relevant_only", "فقط موارد مرتبط"), ("concise", "مختصر")])},
                {"key": "citation_format", "label": "قالب استناد", "type": "select", "options": _opts([("inline", "درون متن"), ("footnotes", "پاورقی"), ("endnotes", "پایان متن"), ("jurisdiction_specific", "قالب متناسب با نظام حقوقی")])},
                {"key": "source_priority", "label": "ترتیب اولویت منابع", "type": "multi_select", "options": _opts([("legislation", "قوانین و مقررات"), ("binding_precedent", "آرای الزام‌آور"), ("persuasive_precedent", "آرای ارشادی و اقناعی"), ("official_guidance", "منابع و راهنمایی رسمی"), ("secondary_sources", "منابع ثانویه")]), "max_items": 5},
                {"key": "citation_verification", "label": "درخواست جزئیات قابل راستی‌آزمایی منبع", "type": "tri_boolean"},
            ],
        },
        {
            "key": "output_formats", "title": "قالب خروجی", "description": "نوع سند و چیدمان پیش‌فرض خروجی‌ها.",
            "fields": [
                {"key": "default_output_types", "label": "خروجی‌های پرکاربرد", "type": "multi_select", "options": _opts([("memo", "یادداشت حقوقی"), ("pleading", "لایحه"), ("petition", "دادخواست"), ("contract", "قرارداد"), ("clause_review", "بررسی بند قرارداد"), ("comparison_table", "جدول مقایسه"), ("executive_summary", "خلاصه مدیریتی"), ("other", "سایر")]), "max_items": 8},
                {"key": "heading_style", "label": "سبک تیترگذاری", "type": "select", "options": _opts([("numbered", "شماره‌گذاری‌شده"), ("descriptive", "توصیفی"), ("minimal", "حداقلی")])},
                {"key": "include_executive_summary", "label": "درج خلاصه مدیریتی", "type": "tri_boolean"},
                {"key": "include_action_items", "label": "درج اقدامات پیشنهادی", "type": "tri_boolean"},
                {"key": "format_note", "label": "توضیح تکمیلی قالب خروجی", "type": "textarea", "max_length": 500},
            ],
        },
        {
            "key": "document_review", "title": "بررسی اسناد و قراردادها", "description": "تمرکزهای ترجیحی هنگام بازبینی و مقایسه اسناد.",
            "fields": [
                {"key": "review_focus", "label": "محورهای بررسی", "type": "multi_select", "options": _opts([("obligations", "تعهدات"), ("deadlines", "مهلت‌ها"), ("payment", "پرداخت"), ("liability", "مسئولیت"), ("termination", "فسخ و خاتمه"), ("dispute_resolution", "حل اختلاف"), ("confidentiality", "محرمانگی"), ("data_protection", "حفاظت داده"), ("other", "سایر")]), "max_items": 9},
                {"key": "comparison_mode", "label": "روش مقایسه", "type": "select", "options": _opts([("summarize_differences", "خلاصه تفاوت‌ها"), ("identify_potential_conflicts", "شناسایی تعارض‌های احتمالی"), ("clause_by_clause", "مقایسه بندبه‌بند")])},
                {"key": "evidence_display", "label": "نمایش عبارت پشتیبان و محل آن در سند", "type": "tri_boolean"},
                {"key": "missing_information_behavior", "label": "رفتار در برابر اطلاعات ناقص", "type": "select", "options": _opts([("ask_questions", "پرسیدن سؤال"), ("list_assumptions", "فهرست‌کردن فرض‌ها"), ("both", "هر دو")])},
            ],
        },
        {
            "key": "assistant_interaction", "title": "شیوه تعامل با دستیار", "description": "میزان پیش‌دستی و نحوه طرح پرسش و توضیح.",
            "fields": [
                {"key": "clarification_behavior", "label": "رفتار هنگام ابهام", "type": "select", "options": _opts([("ask_before_material_assumptions", "پرسش پیش از فرض مهم"), ("proceed_with_marked_assumptions", "ادامه با فرض‌های علامت‌گذاری‌شده"), ("balanced", "متعادل")])},
                {"key": "proactivity", "label": "میزان پیش‌دستی دستیار", "type": "select", "options": _opts([("conservative", "محافظه‌کارانه"), ("balanced", "متعادل"), ("proactive", "پیش‌دستانه")])},
                {"key": "explanation_level", "label": "میزان توضیح", "type": "select", "options": _opts([("brief", "مختصر"), ("normal", "معمولی"), ("detailed", "تفصیلی")])},
                {"key": "suggest_next_steps", "label": "پیشنهاد گام بعدی", "type": "tri_boolean"},
            ],
        },
    ],
}

# Controlled feedback signals. Suggestions are proposals only and are never stored.
FEEDBACK_SIGNALS = [
    {"value": "too_long", "label": "پاسخ بیش از حد طولانی بود"},
    {"value": "too_short", "label": "پاسخ بیش از حد کوتاه بود"},
    {"value": "too_formal", "label": "لحن بیش از حد رسمی بود"},
    {"value": "too_technical", "label": "زبان بیش از حد تخصصی بود"},
    {"value": "too_simple", "label": "زبان بیش از حد ساده بود"},
    {"value": "too_many_citations", "label": "استنادها بیش از حد زیاد بودند"},
    {"value": "too_few_citations", "label": "استناد کافی نبود"},
    {"value": "needs_counterarguments", "label": "استدلال طرف مقابل هم بررسی شود"},
    {"value": "needs_executive_summary", "label": "خلاصه مدیریتی لازم بود"},
    {"value": "needs_action_items", "label": "اقدامات بعدی لازم بود"},
    {"value": "needs_clause_by_clause", "label": "مقایسه بندبه‌بند لازم بود"},
    {"value": "needs_uncertainty_flags", "label": "ابهام‌ها و فرض‌ها واضح‌تر شوند"},
]

SUGGESTIONS = {
    "too_long": ("writing_style", "detail_level", "concise", "میزان تفصیل را مختصرتر کنید."),
    "too_short": ("writing_style", "detail_level", "detailed", "میزان تفصیل را بیشتر کنید."),
    "too_formal": ("writing_style", "tone", "neutral", "لحن را از رسمی به خنثی تغییر دهید."),
    "too_technical": ("writing_style", "legal_language", "accessible", "زبان حقوقی را قابل‌فهم‌تر کنید."),
    "too_simple": ("writing_style", "legal_language", "technical", "از زبان حقوقی تخصصی‌تر استفاده کنید."),
    "too_many_citations": ("citations_and_sources", "citation_density", "relevant_only", "استنادها را به موارد مرتبط محدود کنید."),
    "too_few_citations": ("citations_and_sources", "citation_density", "comprehensive", "استنادهای مرتبط را کامل‌تر ارائه کنید."),
    "needs_counterarguments": ("legal_analysis", "counterargument_review", True, "بررسی استدلال طرف مقابل را فعال کنید."),
    "needs_executive_summary": ("output_formats", "include_executive_summary", True, "خلاصه مدیریتی را به خروجی اضافه کنید."),
    "needs_action_items": ("output_formats", "include_action_items", True, "اقدامات پیشنهادی را به خروجی اضافه کنید."),
    "needs_clause_by_clause": ("document_review", "comparison_mode", "clause_by_clause", "مقایسه بندبه‌بند را ترجیح دهید."),
    "needs_uncertainty_flags": ("legal_analysis", "uncertainty_handling", True, "ابهام‌ها و فرض‌ها را صریح‌تر نمایش دهید."),
}


def get_schema():
    result = deepcopy(SCHEMA)
    result["feedback_signals"] = deepcopy(FEEDBACK_SIGNALS)
    result["tri_boolean_options"] = [
        {"value": "", "label": "بدون ترجیح مشخص"},
        {"value": "true", "label": "بله"},
        {"value": "false", "label": "خیر"},
    ]
    return result


def _field_index():
    return {cat["key"]: {f["key"]: f for f in cat["fields"]} for cat in SCHEMA["categories"]}


def normalize_preferences(payload):
    """Validate and normalize a preference draft without persisting it."""
    if not isinstance(payload, dict):
        raise ValueError("ترجیحات باید در قالب یک شیء ارسال شوند.")
    allowed = _field_index()
    unknown_categories = set(payload) - set(allowed)
    if unknown_categories:
        raise ValueError("دسته‌بندی ترجیح نامعتبر است.")
    normalized = {}
    selected = 0
    for category, values in payload.items():
        if not isinstance(values, dict):
            raise ValueError("ساختار دسته‌بندی ترجیحات نامعتبر است.")
        unknown_fields = set(values) - set(allowed[category])
        if unknown_fields:
            raise ValueError("فیلد ترجیح نامعتبر است.")
        clean = {}
        for key, raw in values.items():
            spec = allowed[category][key]
            kind = spec["type"]
            if raw is None or raw == "" or raw == []:
                continue
            if kind == "select":
                choices = {x["value"] for x in spec["options"]}
                value = str(raw)
                if value not in choices:
                    raise ValueError(f"مقدار فیلد «{spec['label']}» معتبر نیست.")
            elif kind == "multi_select":
                if not isinstance(raw, list):
                    raise ValueError(f"فیلد «{spec['label']}» باید چندانتخابی باشد.")
                choices = {x["value"] for x in spec["options"]}
                value = list(dict.fromkeys(str(x) for x in raw if str(x)))
                if len(value) > int(spec.get("max_items", len(choices))) or any(x not in choices for x in value):
                    raise ValueError(f"انتخاب‌های فیلد «{spec['label']}» معتبر نیست.")
                if not value:
                    continue
            elif kind == "tri_boolean":
                if raw is True or raw == "true":
                    value = True
                elif raw is False or raw == "false":
                    value = False
                else:
                    raise ValueError(f"فیلد «{spec['label']}» باید بله یا خیر باشد.")
            elif kind in {"text", "textarea"}:
                value = str(raw).strip()
                if len(value) > int(spec.get("max_length", 500)):
                    raise ValueError(f"فیلد «{spec['label']}» بیش از حد طولانی است.")
                if not value:
                    continue
            else:
                raise ValueError("نوع فیلد پشتیبانی نمی‌شود.")
            clean[key] = value
            selected += 1
        if clean:
            normalized[category] = clean
    return normalized, selected


def suggest_from_feedback(signal):
    signal = str(signal or "").strip()
    if signal not in SUGGESTIONS:
        raise ValueError("نوع بازخورد پشتیبانی نمی‌شود.")
    category, field, value, rationale = SUGGESTIONS[signal]
    return {
        "category": category,
        "field": field,
        "value": value,
        "rationale": rationale,
        "origin": "ai_suggestion",
        "requires_lawyer_confirmation": True,
        "persisted": False,
    }
