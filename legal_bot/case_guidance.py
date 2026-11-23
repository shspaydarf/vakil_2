"""Local-first lawyer-facing case analysis and guidance.

The module intentionally keeps the first analysis layer deterministic and
traceable.  It reuses the existing local case-intelligence engine and does not
make legal conclusions.  Every suggested item is framed as something to review
against the original file and current law.
"""
from __future__ import annotations

import re
from .analysis import analyze
from .next_step import analyze_next_step
from .files import clean_fa
from .legal_packs import build_pack_guidance
from .check_tree import build_check_tree
from .ejare_tree import build_lease_tree
from .contract_tree import build_contract_tree
from .claims_tree import build_claims_tree
from .property_tree import build_property_tree


def _unique(items, limit=10):
    out, seen = [], set()
    for item in items or []:
        value = re.sub(r"\s+", " ", str(item or "")).strip()
        key = value.casefold()
        if not value or key in seen:
            continue
        seen.add(key); out.append(value)
        if len(out) >= limit:
            break
    return out


def _pages_text(item):
    pages = item.get("source_pages") or item.get("pages") or [] if isinstance(item, dict) else []
    return pages


def _defense_review(ci, result):
    """Produce review questions, not assertions about a winning defence."""
    out = []
    for item in ci.get("missing_items") or []:
        msg = item.get("message") if isinstance(item, dict) else str(item)
        if msg:
            out.append(f"بررسی کنید: {msg}")

    if result.get("contradictions"):
        out.append("اعداد و تاریخ‌های متفاوت را با اصل اسناد و ترتیب زمانی پرونده تطبیق دهید.")

    for item in (ci.get("evidence_matrix") or [])[:10]:
        if isinstance(item, dict) and not item.get("evidence"):
            claim = (item.get("claim") or "").strip()
            if claim:
                out.append(f"برای این ادعا، دلیل مستقل یا مستند پشتیبان را بررسی کنید: {claim[:220]}")

    for item in (ci.get("intelligence_flags") or [])[:7]:
        msg = item.get("message") if isinstance(item, dict) else str(item)
        if msg:
            out.append(msg)

    for item in (result.get("sensitive_clauses") or [])[:8]:
        if isinstance(item, dict) and item.get("label"):
            out.append(f"بند «{item['label']}» را با خواسته/دفاع و سایر مفاد سند تطبیق دهید.")
    return _unique(out, 12)


def _actions(result, next_step):
    actions = []
    if next_step.get("action"):
        actions.append(next_step["action"])
    for item in next_step.get("missing") or []:
        actions.append(f"تکمیل/بررسی: {item}")
    ci = result.get("case_intelligence") or {}
    if not ci.get("issues"):
        actions.append("موضوع اصلی پرونده را از متن اسناد و خواسته‌ها دقیق‌تر مشخص کنید.")
    if not result.get("legal_references"):
        actions.append("مبنای قانونی ادعاها و دفاعیات را با جستجوی قوانین و مقررات مرتبط بررسی کنید.")
    if result.get("contradictions"):
        actions.append("اختلاف اعداد یا تاریخ‌ها را قبل از اتکا در هر اقدام بعدی با اصل سند تطبیق دهید.")
    if result.get("missing_items"):
        actions.append("موارد ناقص فهرست‌شده را از اصل پرونده یا اسناد تکمیلی کنترل کنید.")
    return _unique(actions, 10)


def _questions(result, next_step):
    """Deterministic questions a lawyer can answer to deepen the analysis."""
    questions = []
    ci = result.get("case_intelligence") or {}
    for item in ci.get("missing_items") or []:
        msg = item.get("message") if isinstance(item, dict) else str(item)
        if msg:
            questions.append(f"آیا {msg.rstrip('؟')} در اصل پرونده/سامانه موجود است؟")
    if result.get("claims"):
        questions.append("خواسته یا ادعای اصلی دقیقاً با متن سند و آخرین وضعیت پرونده منطبق است؟")
    if result.get("legal_references"):
        questions.append("آیا مواد قانونی اشاره‌شده هنوز معتبرند و با وضعیت زمانی پرونده انطباق دارند؟")
    if result.get("sensitive_clauses"):
        questions.append("آیا بندهای حساس قرارداد/سند با سایر بندها، الحاقیه‌ها و اقدامات بعدی تعارض ندارند؟")
    if next_step.get("stage") in {"ابلاغ", "دادخواست/شروع دعوا", "رأی/حکم", "اجرای حکم"}:
        questions.append("آخرین ابلاغ معتبر پرونده چه زمانی انجام شده و اثر آن بر مهلت‌های احتمالی چیست؟")
    return _unique(questions, 8)


def _pack_list(items, key, limit=10):
    out = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        value = item.get(key) or item.get("text") or item.get("value") or ""
        if not value:
            continue
        out.append({"text": str(value)[:700], "pages": _pages_text(item)})
        if len(out) >= limit:
            break
    return out



def _unified_tree_analysis(text):
    """Run specialized trees as internal analysis modules, never as user-facing menus."""
    builders = [
        ("چک و اسناد تجاری", build_check_tree, "is_check"),
        ("اجاره و تخلیه", build_lease_tree, "is_lease"),
        ("قرارداد و تعهدات", build_contract_tree, "is_contract"),
        ("مطالبات و دیون", build_claims_tree, "is_debt"),
        ("املاک و مالکیت", build_property_tree, "is_property"),
    ]
    domains=[]
    for label, builder, flag in builders:
        try:
            result=builder(text) or {}
        except Exception:
            continue
        if not result.get(flag):
            continue
        nodes=[]
        for node in (result.get("nodes") or [])[:8]:
            if isinstance(node, dict):
                value=node.get("result") or node.get("label") or ""
                if value: nodes.append(str(value)[:320])
        domains.append({
            "domain": label,
            "findings": _unique(nodes, 8),
            "questions": _unique(result.get("questions") or [], 6),
            "missing": _unique(result.get("missing") or [], 6),
            "flags": _unique(result.get("flags") or result.get("branches") or result.get("paths") or [], 6),
            "source_count": len(result.get("sources") or []),
        })
    return domains

def build_case_guidance(text: str):
    text = clean_fa(text or "")
    if len(text.strip()) < 40:
        return {"sufficient": False, "reason": "متن پرونده برای تحلیل پایه کافی نیست.", "ai_used": False}

    result = analyze(text)
    ci = result.get("case_intelligence") or {}
    next_step = analyze_next_step(text)
    legal_packs = build_pack_guidance(text)
    tree_analysis = _unified_tree_analysis(text)

    facts = []
    for item in (ci.get("key_facts") or [])[:15]:
        if isinstance(item, dict):
            value = item.get("fact") or ""
            if value:
                facts.append({"text": value[:420], "pages": item.get("source_pages") or []})

    issues = []
    for item in (ci.get("issues") or [])[:12]:
        if not isinstance(item, dict):
            continue
        pages = sorted({p for signal in (item.get("signals") or []) for p in (signal.get("source_pages") or [])})
        if item.get("issue"):
            issues.append({"text": item["issue"][:500], "pages": pages})

    missing = []
    for item in (ci.get("missing_items") or [])[:12]:
        if isinstance(item, dict):
            msg = item.get("message") or item.get("item") or ""
            if msg: missing.append(msg)

    evidence = []
    for item in (ci.get("evidence_matrix") or [])[:12]:
        if not isinstance(item, dict):
            continue
        evidence.append({
            "claim": (item.get("claim") or "")[:360],
            "supported": bool(item.get("evidence")),
            "pages": item.get("claim_source_pages") or [],
            "evidence_pages": item.get("evidence_source_pages") or [],
        })

    parties = []
    for item in (result.get("parties") or [])[:12]:
        if isinstance(item, dict) and item.get("name"):
            parties.append({"name": item.get("name"), "role": item.get("role") or "", "pages": item.get("source_pages") or []})

    amounts = _pack_list(result.get("amounts"), "value", 10)
    dates = _pack_list(result.get("dates"), "value", 15)
    claims = _pack_list(result.get("claims"), "claim", 10)
    refs = _pack_list(result.get("legal_references"), "reference", 12)
    sensitive = _pack_list(result.get("sensitive_clauses"), "text", 10)
    timeline = _pack_list(result.get("timeline"), "event", 15)
    risks = _pack_list(result.get("risks"), "message", 10)
    contradictions = _pack_list(result.get("contradictions"), "message", 10)

    return {
        "sufficient": True,
        "ai_used": False,
        "engine": "local-rule-based-v3",
        "document_type": ci.get("document_type") or result.get("document_type") or "نامشخص",
        "stage": next_step.get("stage") or "مرحله نامشخص",
        "overview": _unique(result.get("overview") or [], 8),
        "parties": parties,
        "facts": facts,
        "claims": claims,
        "issues": issues,
        "missing": _unique(missing, 10),
        "evidence": evidence,
        "legal_references": refs,
        "sensitive_clauses": sensitive,
        "timeline": timeline,
        "amounts": amounts,
        "dates": dates,
        "risks": risks,
        "contradictions": contradictions,
        "review_points": _defense_review(ci, result),
        "questions": _questions(result, next_step),
        "actions": _actions(result, next_step),
        "future_dates": next_step.get("future_dates") or [],
        "legal_packs": legal_packs,
        "specialized_analysis": tree_analysis,
        "source_stats": result.get("stats") or {},
        "warning": (
            "این خروجی تحلیل پایه و استخراجی است. پیشنهادها تصمیم حقوقی قطعی نیستند؛ "
            "پیدا نشدن یک مورد در متن به معنی نبودن آن در اصل پرونده نیست و "
            "قوانین، مهلت‌ها و اعتبار منابع باید با وضعیت روز و اصل اسناد تطبیق داده شوند."
        ),
    }


def format_case_guidance(guidance):
    if not guidance.get("sufficient"):
        return "🧠 تحلیل و پیشنهادات پرونده\n\n⚠️ " + guidance.get("reason", "اطلاعات کافی نیست.")

    lines = [
        "🧠 تحلیلگر پرونده", "",
        "🔒 موتور: تحلیل داخلی و بدون AI",
        f"📄 نوع سند احتمالی: {guidance.get('document_type') or 'نامشخص'}",
        f"📌 وضعیت قابل تشخیص از متن: {guidance.get('stage') or 'نامشخص'}",
    ]

    sections = [
        ("📋 تصویر کلی پرونده:", guidance.get("overview"), lambda x: "• " + x),
    ]
    for title, values, renderer in sections:
        if values:
            lines += ["", title] + [renderer(x) for x in values[:8]]

    if guidance.get("parties"):
        lines += ["", "👥 اشخاص/نقش‌های شناسایی‌شده:"]
        for x in guidance["parties"][:10]:
            role = f" — {x['role']}" if x.get("role") else ""
            pages = f" — ص {', '.join(map(str, x['pages']))}" if x.get("pages") else ""
            lines.append(f"• {x['name']}{role}{pages}")

    if guidance.get("claims"):
        lines += ["", "🎯 ادعاها/خواسته‌های قابل مشاهده:"]
        for x in guidance["claims"][:8]:
            pages = f" — ص {', '.join(map(str, x['pages']))}" if x.get("pages") else ""
            lines.append(f"• {x['text']}{pages}")

    if guidance.get("facts"):
        lines += ["", "🔵 واقعیت‌ها/اطلاعات استخراج‌شده:"]
        for x in guidance["facts"][:10]:
            pages = f" — ص {', '.join(map(str, x['pages']))}" if x.get("pages") else ""
            lines.append("• " + x["text"] + pages)

    if guidance.get("issues"):
        lines += ["", "🎯 مسائل و محورهای قابل بررسی:"]
        for x in guidance["issues"][:10]:
            pages = f" — ص {', '.join(map(str, x['pages']))}" if x.get("pages") else ""
            lines.append("• " + x["text"] + pages)

    if guidance.get("specialized_analysis"):
        lines += ["", "🧩 تحلیل تخصصی موضوعات پرونده:"]
        for item in guidance["specialized_analysis"]:
            lines.append(f"• {item['domain']}")
            for finding in item.get("findings", [])[:4]:
                lines.append(f"  - {finding}")
            for flag in item.get("flags", [])[:3]:
                lines.append(f"  - محور بررسی: {flag}")
        lines.append("↳ این بخش حاصل اجرای داخلی موتورهای تخصصی است و به‌منزله نتیجه قطعی حقوقی نیست.")

    if guidance.get("legal_references"):
        lines += ["", "⚖️ مواد/منابع حقوقی که در متن پرونده به آنها اشاره شده:"]
        for x in guidance["legal_references"][:10]:
            pages = f" — ص {', '.join(map(str, x['pages']))}" if x.get("pages") else ""
            lines.append("• " + x["text"] + pages)
        lines.append("↳ برای یافتن قوانین و منابع بیشتر، از «مواد و مقررات مرتبط» استفاده کنید.")

    if guidance.get("legal_packs"):
        lines += ["", "🧩 بسته‌های تخصصی فعال‌شده از روی متن پرونده:"]
        for pack in guidance["legal_packs"]:
            lines += [f"", f"━━ {pack['title']} ━━"]
            if pack.get("signals"):
                lines.append("🔎 نشانه‌های تشخیص: " + "، ".join(pack["signals"][:6]))
            if pack.get("sources"):
                lines.append("⚖️ مبانی/منابع برای کنترل:")
                lines.extend("• " + x for x in pack["sources"][:5])
            if pack.get("source_candidates"):
                lines.append("📚 منابع موجود در مخزن داخلی بات:")
                for src in pack["source_candidates"][:6]:
                    extra = f" — {src['articles']} ماده" if src.get("articles") else ""
                    lines.append(f"• {src.get('title','')}" + extra)
            if pack.get("related_rulings"):
                lines.append("⚖️ آرای مرتبطِ قابل جستجو در مخزن داخلی:")
                for src in pack["related_rulings"][:4]:
                    lines.append(f"• رأی {src.get('number','')} — {src.get('date','')} — {src.get('title','')}")
            if pack.get("related_consultations"):
                lines.append("📝 نظریات مشورتی مرتبطِ قابل جستجو:")
                for src in pack["related_consultations"][:3]:
                    lines.append(f"• {src.get('number','')} — {src.get('date','')} — {src.get('title','')}")
                lines.append("↳ نظریه مشورتی منبع ارشادی است و با قانون/رأی الزام‌آور یکسان نیست.")
            if pack.get("issues"):
                lines.append("🧭 محورهای تخصصی بررسی:")
                lines.extend("• " + x for x in pack["issues"][:5])
            if pack.get("docs"):
                lines.append("📎 مدارک مهم: " + "، ".join(pack["docs"][:6]))
            if pack.get("evidence"):
                lines.append("🔍 شواهدی که ارزش تطبیق دارند: " + "، ".join(pack["evidence"][:6]))
            if pack.get("questions"):
                lines.append("❓ سؤال‌های کلیدی: " + " | ".join(pack["questions"][:4]))
            if pack.get("actions"):
                lines.append("➡️ اقدام‌های پیشنهادی: " + " | ".join(pack["actions"][:4]))
            if pack.get("red_flags"):
                lines.append("🚩 پرچم‌های بررسی: " + "، ".join(pack["red_flags"][:5]))
        lines.append("↳ فعال‌شدن بسته به معنی احراز موضوع یا صحت ادعا نیست؛ فقط از روی نشانه‌های متن پرونده است.")

    if guidance.get("evidence"):
        lines += ["", "📑 ادعا و نشانه دلیل:"]
        for x in guidance["evidence"][:8]:
            mark = "✓ نشانه مرتبط پیدا شد" if x["supported"] else "؟ دلیل مرتبط در متن استخراج‌شده پیدا نشد"
            pages = x.get("evidence_pages") or x.get("pages") or []
            suffix = f" — ص {', '.join(map(str, pages))}" if pages else ""
            lines.append(f"• {mark}: {x['claim']}{suffix}")

    if guidance.get("sensitive_clauses"):
        lines += ["", "🔎 بندها/عبارت‌های حساس برای تطبیق:"]
        for x in guidance["sensitive_clauses"][:8]:
            pages = f" — ص {', '.join(map(str, x['pages']))}" if x.get("pages") else ""
            lines.append(f"• {x['text']}{pages}")

    if guidance.get("missing"):
        lines += ["", "⚠️ خلأهای اطلاعاتی در متن استخراج‌شده:"]
        lines += ["• " + x for x in guidance["missing"][:8]]

    if guidance.get("contradictions"):
        lines += ["", "⚠️ موارد نیازمند تطبیق/احتمال تعارض:"]
        lines += ["• " + x["text"] for x in guidance["contradictions"][:6]]

    if guidance.get("risks"):
        lines += ["", "🟠 هشدارهای موتور تحلیل:"]
        lines += ["• " + x["text"] for x in guidance["risks"][:6]]

    if guidance.get("review_points"):
        lines += ["", "🛡 محورهای دفاع/پاسخ که ارزش بررسی دارند:"]
        lines += ["• " + x for x in guidance["review_points"][:8]]

    if guidance.get("questions"):
        lines += ["", "❓ پرسش‌هایی که پاسخشان می‌تواند تحلیل را دقیق‌تر کند:"]
        lines += ["• " + x for x in guidance["questions"][:7]]

    if guidance.get("actions"):
        lines += ["", "➡️ اقدامات قابل بررسی بعدی:"]
        lines += ["• " + x for x in guidance["actions"][:8]]

    if guidance.get("amounts"):
        lines += ["", "💰 مبالغ/ارقام مالی پیدا‌شده:"]
        for x in guidance["amounts"][:8]:
            pages = f" — ص {', '.join(map(str, x['pages']))}" if x.get("pages") else ""
            lines.append("• " + x["text"] + pages)

    if guidance.get("dates"):
        lines += ["", "📅 تاریخ‌های ذکرشده در متن:"]
        for x in guidance["dates"][:10]:
            pages = f" — ص {', '.join(map(str, x['pages']))}" if x.get("pages") else ""
            lines.append("• " + x["text"] + pages)

    if guidance.get("future_dates"):
        lines += ["", "⏰ تاریخ‌هایی که موتور تقویم برای کنترل آینده تشخیص داده:"]
        for item in guidance["future_dates"][:5]:
            if isinstance(item, dict):
                value = item.get("date_jalali") or item.get("raw_value") or ""
                desc = item.get("description") or "تاریخ ذکرشده در پرونده"
                lines.append(f"• {value} — {desc}")

    if guidance.get("timeline"):
        lines += ["", "🕘 خط زمانی استخراج‌شده (بدون ساختن ترتیب جدید):"]
        for x in guidance["timeline"][:10]:
            lines.append("• " + x["text"])

    lines += ["", "⚠️ " + guidance["warning"]]
    return "\n".join(lines)
