"""Deterministic cheque decision tree for the active case.

This is an issue-spotting workflow, not a legal opinion. It uses the case text,
the internal legal corpus, and conservative branch labels. Exact legal deadlines
and applicability must be checked against the current primary source.
"""
from __future__ import annotations

import re
from .files import clean_fa
from .legal_packs import _corpus, _norm
from functools import partial
from .text_utils import has_any_normalized_term, find_law_source_hits


_has = partial(has_any_normalized_term, normalizer=_norm)


_source_hits = partial(find_law_source_hits, corpus_loader=_corpus, normalizer=_norm)


def build_check_tree(text: str):
    text = clean_fa(text or "")
    if len(text.strip()) < 40:
        return {"sufficient": False, "reason": "متن پرونده برای ساخت مسیر بررسی چک کافی نیست."}

    t = _norm(text)
    is_check = _has(t, "چک", "صیادی", "گواهی عدم پرداخت", "صادرکننده چک", "دارنده چک")
    if not is_check:
        return {
            "sufficient": True, "is_check": False,
            "title": "🌳 درخت بررسی چک",
            "message": "در متن پرونده نشانه کافی از چک پیدا نشد. اگر چک بخشی از پرونده است، اصل چک یا بخش مرتبط را به پرونده اضافه کنید."
        }

    nodes = []
    questions = []
    missing = []
    branches = []

    # Node 1: instrument type
    if _has(t, "صیادی", "سامانه صیاد"):
        typ = "چک با نشانه صیادی"
        questions.append("وضعیت ثبت، تأیید و انتقال در سامانه صیاد چیست؟")
        missing.append("سابقه/وضعیت ثبت و انتقال در سامانه صیاد")
    else:
        typ = "نوع چک از متن قطعی نیست"
        questions.append("آیا چک صیادی است یا غیرصیادی و وضعیت ثبت/انتقال آن چگونه است؟")
        missing.append("نوع دقیق چک و وضعیت ثبت/انتقال")
    nodes.append({"id": "type", "label": "۱) نوع و وضعیت سند", "result": typ})

    # Node 2: payment / bank certificate
    returned = _has(t, "گواهی عدم پرداخت", "عدم پرداخت", "برگشت چک", "چک برگشتی", "کسری موجودی")
    if returned:
        result = "نشانه عدم پرداخت/برگشت وجود دارد"
        questions.append("تاریخ مراجعه به بانک و تاریخ/محتوای گواهی عدم پرداخت دقیقاً چیست؟")
        if not _has(t, "گواهی عدم پرداخت"):
            missing.append("اصل یا تصویر خوانای گواهی عدم پرداخت")
    else:
        result = "عدم پرداخت از متن قطعی نیست"
        questions.append("آیا چک به بانک ارائه شده و گواهی عدم پرداخت صادر شده است؟")
        missing.append("وضعیت ارائه به بانک و گواهی عدم پرداخت")
    nodes.append({"id": "bank", "label": "۲) وضعیت بانک", "result": result})

    # Node 3: dates
    has_dates = bool(re.search(r"\d{1,4}[/-]\d{1,2}[/-]\d{1,4}", text)) or _has(t, "تاریخ صدور", "تاریخ سررسید", "تاریخ چک")
    if has_dates:
        result = "تاریخ‌هایی در متن دیده می‌شود؛ باید با اصل چک و گواهی بانک تطبیق شوند"
    else:
        result = "تاریخ‌های کلیدی کافی در متن پیدا نشد"
        missing.append("تاریخ صدور، تاریخ درج‌شده روی چک، مراجعه به بانک و گواهی عدم پرداخت")
    questions.append("آیا ترتیب تاریخ صدور/سررسید، مراجعه به بانک و گواهی عدم پرداخت مشخص و مستند است؟")
    nodes.append({"id": "dates", "label": "۳) خط زمانی", "result": result})

    # Node 4: underlying relationship
    if _has(t, "قرارداد", "معامله", "ثمن", "خرید", "فروش", "اجاره", "بابت", "تعهد"):
        result = "برای چک رابطه پایه/قراردادی در متن دیده می‌شود"
        questions.append("مبنای صدور چک و تعهد پایه دقیقاً چیست و آیا سند آن در پرونده موجود است؟")
    else:
        result = "رابطه پایه در متن روشن نیست"
        missing.append("قرارداد/معامله یا توضیح مستند درباره علت صدور چک")
        questions.append("چک بابت چه رابطه‌ای صادر شده است؟")
    nodes.append({"id": "base", "label": "۴) رابطه پایه", "result": result})

    # Node 5: special purpose
    special = []
    if _has(t, "تضمینی", "ضمانتی"):
        special.append("تضمینی")
    if _has(t, "مشروط", "شرطی"):
        special.append("مشروط")
    if _has(t, "امانی", "امانت"):
        special.append("امانی")
    if _has(t, "وعده دار", "وعده‌دار"):
        special.append("وعده‌دار")
    if special:
        result = "ادعای وضعیت خاص: " + "، ".join(dict.fromkeys(special))
        questions.append("برای این وصف خاص چه سند، شرط قراردادی یا قرینه مستقلی وجود دارد؟")
        missing.append("مستند ادعای تضمینی/مشروط/امانی/وعده‌دار بودن در صورت وجود")
    else:
        result = "وصف خاصی از متن قطعی نیست"
        questions.append("آیا چک تضمینی، مشروط، امانی یا بابت تعهد خاص صادر شده است؟")
    nodes.append({"id": "special", "label": "۵) وصف خاص چک", "result": result})

    # Node 6: parties and transfer
    transfer = _has(t, "ظهرنویس", "ظهرنویسی", "انتقال", "دارنده جدید", "واگذار", "سامانه صیاد")
    if transfer:
        result = "نشانه انتقال/تغییر دارنده وجود دارد"
        questions.append("زنجیره انتقال و سمت دارنده فعلی چگونه اثبات می‌شود؟")
        missing.append("مدرک انتقال/ظهرنویسی و مشخصات دارنده فعلی")
    else:
        result = "انتقال یا ظهرنویسی از متن روشن نیست"
        questions.append("آیا چک به شخص دیگری منتقل شده است؟")
    nodes.append({"id": "holder", "label": "۶) دارنده و انتقال", "result": result})

    # Node 7: post-issuance events
    if _has(t, "پرداخت جزئی", "بخشی از مبلغ", "تسویه", "توافق", "استرداد چک", "پرداخت شد"):
        result = "نشانه پرداخت/توافق بعدی وجود دارد"
        questions.append("مبلغ و تاریخ هر پرداخت یا توافق بعدی چیست و آیا رسید معتبر وجود دارد؟")
        missing.append("رسید پرداخت/تسویه یا توافق بعدی")
    else:
        result = "پرداخت یا توافق بعدی از متن روشن نیست"
        questions.append("آیا پس از صدور چک پرداخت، توافق، تمدید یا استردادی انجام شده است؟")
    nodes.append({"id": "after", "label": "۷) رویدادهای بعدی", "result": result})

    # Node 8: possible paths (not conclusions)
    paths = ["مطالبه/پیگیری حقوقی"]
    if returned:
        paths.append("بررسی مسیر اجرایی/ثبتی، در صورت احراز شرایط")
        paths.append("بررسی جداگانه امکان مسیر کیفری، با کنترل شرایط و مهلت‌های قانونی")
    branches.extend(paths)
    nodes.append({"id": "paths", "label": "۸) مسیرهای قابل بررسی", "result": " / ".join(paths)})

    # High-risk review flags
    flags = []
    if _has(t, "تاریخ متفاوت", "تاریخ جعلی", "دستکاری", "الحاق", "مخدوش"):
        flags.append("ادعای اختلاف/دستکاری در تاریخ یا متن چک")
    if _has(t, "مبلغ متفاوت", "مغایرت مبلغ", "عدد و حروف"):
        flags.append("مغایرت مبلغ یا نحوه درج مبلغ")
    if _has(t, "فوت", "ورشکستگی"):
        flags.append("وضعیت خاص صادرکننده (فوت/ورشکستگی) نیازمند بررسی مستقل")
    if special:
        flags.append("وصف خاص چک می‌تواند مسیر بررسی را تغییر دهد؛ مستند آن باید کنترل شود")
    if transfer:
        flags.append("زنجیره انتقال و سمت دارنده فعلی باید مستند شود")

    sources = _source_hits(["قانون صدور چک", "قانون تجارت", "قانون آیین دادرسی مدنی", "قانون نحوه اجرای محکومیت‌های مالی"], 8)
    return {
        "sufficient": True, "is_check": True, "title": "🌳 درخت بررسی چک",
        "type": typ, "nodes": nodes, "branches": branches,
        "questions": list(dict.fromkeys(questions))[:12],
        "missing": list(dict.fromkeys(missing))[:10],
        "flags": list(dict.fromkeys(flags))[:8],
        "sources": sources,
        "warning": "این درخت برای issue-spotting و نظم‌دهی بررسی پرونده است، نه اعلام نتیجه قطعی. شرایط هر مسیر و مهلت‌ها باید با متن قانون و اصل اسناد پرونده تطبیق داده شوند."
    }


def format_check_tree(tree):
    if not tree.get("sufficient"):
        return "🌳 درخت بررسی چک\n\n⚠️ " + tree.get("reason", "اطلاعات کافی نیست.")
    if not tree.get("is_check"):
        return f"{tree.get('title', '🌳 درخت بررسی چک')}\n\nℹ️ {tree.get('message', '')}"

    lines = [tree.get("title", "🌳 درخت بررسی چک"), "", "🔒 موتور: درخت تصمیم داخلی و بدون AI", ""]
    lines.append("🧭 مسیر تشخیص:")
    for node in tree.get("nodes", []):
        lines.append(f"• {node['label']}: {node['result']}")

    if tree.get("branches"):
        lines += ["", "🛣️ مسیرهای قابل بررسی:"]
        for x in tree["branches"]:
            lines.append("• " + x)

    if tree.get("missing"):
        lines += ["", "📂 اطلاعات/مدارک ناقص یا نیازمند کنترل:"]
        for x in tree["missing"][:10]: lines.append("• " + x)

    if tree.get("questions"):
        lines += ["", "❓ سؤال‌های بعدی و کلیدی:"]
        for i, x in enumerate(tree["questions"][:12], 1): lines.append(f"{i}. {x}")

    if tree.get("flags"):
        lines += ["", "🚩 نقاط حساس:"]
        for x in tree["flags"]: lines.append("• " + x)

    if tree.get("sources"):
        lines += ["", "📚 منابع داخلی قابل بررسی:"]
        for x in tree["sources"]:
            lines.append("• " + x["title"])

    lines += ["", "⚠️ " + tree.get("warning", "")] 
    return "\n".join(lines)

# --- Interactive workflow layer (V150) ---
_INTERACTIVE_NODES = [
    {
        "id": "instrument",
        "title": "۱) نوع و وضعیت چک",
        "question": "نوع و وضعیت چک کدام است؟",
        "choices": [("صیادی", "s"), ("غیرصیادی", "n"), ("نامشخص", "u")],
    },
    {
        "id": "bank",
        "title": "۲) وضعیت بانک",
        "question": "وضعیت ارائه به بانک و عدم پرداخت چیست؟",
        "choices": [("گواهی عدم پرداخت دارم", "r"), ("هنوز ارائه نشده", "p"), ("نامشخص", "u")],
    },
    {
        "id": "purpose",
        "title": "۳) رابطه پایه / وصف چک",
        "question": "وضعیت رابطه پایه یا وصف خاص چک چیست؟",
        "choices": [("عادی/بابت دین", "d"), ("تضمینی", "g"), ("مشروط/امانی", "c"), ("نامشخص", "u")],
    },
    {
        "id": "holder",
        "title": "۴) دارنده و انتقال",
        "question": "وضعیت دارنده فعلی چگونه است؟",
        "choices": [("صادرکننده/دارنده اولیه", "o"), ("منتقل شده", "t"), ("نامشخص", "u")],
    },
    {
        "id": "payment",
        "title": "۵) پرداخت‌های بعدی",
        "question": "پس از صدور یا برگشت چک پرداخت یا توافقی انجام شده؟",
        "choices": [("خیر", "n"), ("بله", "y"), ("نامشخص", "u")],
    },
]


def interactive_check_start(text: str):
    base = build_check_tree(text)
    if not base.get("is_check"):
        return {"status": "not_check", "base": base}
    return {"status": "active", "base": base, "index": 0, "answers": {}, "history": []}


def interactive_check_step(state, choice):
    """Apply one deterministic answer and return the next node or completion."""
    if not state or state.get("status") != "active":
        return {"status": "invalid"}
    idx = int(state.get("index", 0))
    if idx >= len(_INTERACTIVE_NODES):
        return interactive_check_finalize(state)
    node = _INTERACTIVE_NODES[idx]
    valid = {code for _, code in node["choices"]}
    if choice not in valid:
        return {"status": "invalid", "state": state}
    state.setdefault("answers", {})[node["id"]] = choice
    state.setdefault("history", []).append(idx)
    state["index"] = idx + 1
    if state["index"] >= len(_INTERACTIVE_NODES):
        return interactive_check_finalize(state)
    return {"status": "question", "state": state, "node": _INTERACTIVE_NODES[state["index"]]}


def interactive_check_finalize(state):
    answers = state.get("answers", {})
    base = state.get("base", {})
    findings = []
    missing = list(base.get("missing", []))
    paths = list(base.get("branches", []))
    if answers.get("instrument") == "s":
        findings.append("ثبت/تأیید/انتقال صیادی باید با سابقه سامانه تطبیق شود.")
        if "سابقه/وضعیت ثبت و انتقال در سامانه صیاد" not in missing:
            missing.append("سابقه/وضعیت ثبت و انتقال در سامانه صیاد")
    elif answers.get("instrument") == "u":
        missing.append("نوع دقیق چک و وضعیت سامانه صیاد")
    if answers.get("bank") == "r":
        findings.append("گواهی عدم پرداخت به‌عنوان سند محوری مسیرهای بعدی باید با اصل/نسخه معتبر تطبیق شود.")
    elif answers.get("bank") == "p":
        findings.append("قبل از بررسی مسیرهای مبتنی بر عدم پرداخت، وضعیت ارائه به بانک باید روشن شود.")
    else:
        missing.append("وضعیت قطعی ارائه به بانک و گواهی عدم پرداخت")
    if answers.get("purpose") in ("g", "c"):
        findings.append("وصف خاص چک نیازمند بررسی سند رابطه پایه و شرایط قراردادی است و به‌تنهایی نتیجه حقوقی قطعی ایجاد نمی‌کند.")
    if answers.get("holder") == "t":
        findings.append("سمت دارنده فعلی و زنجیره انتقال باید مستند و با اطلاعات سامانه/ظهرنویسی تطبیق شود.")
    if answers.get("payment") == "y":
        findings.append("پرداخت یا توافق بعدی می‌تواند بر مبلغ مورد مطالبه و وضعیت تعهد اثر بگذارد؛ رسیدها باید تطبیق شوند.")
    if answers.get("payment") == "u":
        missing.append("سوابق پرداخت، تسویه، تمدید یا توافق بعدی")
    # Keep source information centralized in the base tree.
    return {
        "status": "complete",
        "state": state,
        "findings": list(dict.fromkeys(findings)),
        "missing": list(dict.fromkeys(missing))[:14],
        "paths": list(dict.fromkeys(paths)),
        "sources": base.get("sources", []),
        "warning": base.get("warning", ""),
    }


def format_interactive_question(node, step, total):
    lines = ["🌳 درخت تعاملی بررسی چک", "", f"مرحله {step} از {total}", "", f"❓ {node['question']}", "", "🔒 تحلیل داخلی و بدون AI"]
    return "\n".join(lines)


def format_interactive_result(result):
    if result.get("status") == "not_check":
        return format_check_tree(result.get("base", {}))
    if result.get("status") != "complete":
        return "❌ وضعیت درخت قابل ادامه نیست. دوباره درخت بررسی چک را باز کنید."
    lines = ["🌳 نتیجه درخت تعاملی بررسی چک", "", "🧩 یافته‌های حاصل از پاسخ‌های پرونده:"]
    for x in result.get("findings", []):
        lines.append("• " + x)
    if result.get("paths"):
        lines += ["", "🛣️ مسیرهای قابل بررسی:"]
        for x in result["paths"]:
            lines.append("• " + x)
    if result.get("missing"):
        lines += ["", "📂 اطلاعات/مدارک هنوز نیازمند کنترل:"]
        for x in result["missing"]:
            lines.append("• " + x)
    if result.get("sources"):
        lines += ["", "📚 منابع داخلی قابل بررسی:"]
        for x in result["sources"]:
            lines.append("• " + x["title"])
    lines += ["", "⚠️ " + result.get("warning", "")]
    return "\n".join(lines)
