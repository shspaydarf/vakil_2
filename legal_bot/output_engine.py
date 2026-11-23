# -*- coding: utf-8 -*-
"""V160 — presentation/export layer for the V159-gated case draft.

Read-only: this module never changes the legal draft or performs legal reasoning.
It renders the already-gated V158/V159 artifacts for Telegram and copy/export use.
"""
from __future__ import annotations
from copy import deepcopy
from typing import Any, Dict
from io import BytesIO


from .text_guard import normalize_output

VERSION = 160


def _clean(v: Any) -> str:
    return " ".join(str(v or "").split()).strip()


def _status_label(status: str) -> str:
    return "✅ آماده نمایش" if status == "PASS" else "⛔ متوقف برای بررسی وکیل"


def _gate_snapshot(gate: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "status": gate.get("status"),
        "counts": deepcopy(gate.get("counts") or {}),
        "findings": deepcopy(gate.get("findings") or []),
        "requires_lawyer_review": True,
        "legal_conclusion_generated": False,
        "final_brief_generated": False,
        "api_used": False,
    }


def build_case_output(gate: Dict[str, Any]) -> Dict[str, Any]:
    """Build a presentation-only V160 package from a V159 gate result."""
    gate = gate or {}
    revised = deepcopy(gate.get("updated_draft") or {})
    if not revised:
        return {
            "version": VERSION,
            "status": "BLOCKED",
            "error": "خروجی ساختاری V159 موجود نیست.",
            "gate": _gate_snapshot(gate),
            "requires_lawyer_review": True,
            "legal_conclusion_generated": False,
            "final_brief_generated": False,
            "api_used": False,
        }

    # V166.1: the final user-facing boundary is the only place where
    # presentation cleanup is applied. The immutable V159/V158 trace remains
    # untouched in `gate` and `revised`.
    rendered = normalize_output(str(revised.get("rendered_text") or "").strip())
    findings = deepcopy(gate.get("findings") or [])
    # V158 stores the authoritative Change Log at the rewrite envelope; V159
    # now carries it forward explicitly so V160 never loses audit data.
    changes = deepcopy(gate.get("changes") or [])

    return {
        "version": VERSION,
        "case_id": gate.get("case_id") or revised.get("case_id"),
        "draft_id": revised.get("draft_id"),
        "rewrite_id": gate.get("rewrite_id"),
        "status": gate.get("status") or "BLOCKED",
        "status_label": _status_label(gate.get("status") or "BLOCKED"),
        "draft_text": rendered,
        "changes": changes,
        "findings": findings,
        "gate": _gate_snapshot(gate),
        "source_trace": deepcopy(gate.get("source_trace") or revised.get("source_trace") or {}),
        "requires_lawyer_review": True,
        "legal_conclusion_generated": False,
        "final_brief_generated": False,
        "api_used": False,
    }




def _document_text(text: str) -> str:
    """Prepare document text without invisible bidi isolation controls.

    Office layout engines already handle RTL runs. Keeping LRI/PDI in the file
    can make search/copy results surprising, so strip only these presentation
    controls while preserving the actual characters and line breaks.
    """
    value = normalize_output(str(text or '').strip())
    return value.replace('\u2066', '').replace('\u2069', '').replace('\u200e', '').replace('\u200f', '')


def build_case_docx(result: Dict[str, Any]) -> bytes:
    """Create an editable Persian Word document from the gated draft text."""
    from docx import Document
    from docx.shared import Cm, Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.section import WD_SECTION
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    text = _document_text((result or {}).get('draft_text') or '')
    if not text:
        raise ValueError('متن قابل ارائه برای Word وجود ندارد.')

    doc = Document()
    section = doc.sections[0]
    section.page_width = Cm(21)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.2)
    section.bottom_margin = Cm(2.0)
    section.left_margin = Cm(2.2)
    section.right_margin = Cm(2.5)

    normal = doc.styles['Normal']
    normal.font.name = 'Noto Naskh Arabic'
    normal.font.size = Pt(12)
    normal._element.rPr.rFonts.set(qn('w:eastAsia'), 'Noto Naskh Arabic')
    normal._element.rPr.rFonts.set(qn('w:cs'), 'Noto Naskh Arabic')
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.25

    def set_rtl(paragraph):
        paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        p_pr = paragraph._p.get_or_add_pPr()
        bidi = p_pr.find(qn('w:bidi'))
        if bidi is None:
            bidi = OxmlElement('w:bidi')
            p_pr.append(bidi)
        bidi.set(qn('w:val'), '1')

    # Document title is clearly a presentation heading, not added legal content.
    title = doc.add_paragraph()
    set_rtl(title)
    title.paragraph_format.space_after = Pt(16)
    run = title.add_run('پیش‌نویس لایحه دفاعیه')
    run.bold = True
    run.font.name = 'Noto Naskh Arabic'
    run.font.size = Pt(16)
    run._element.rPr.rFonts.set(qn('w:cs'), 'Noto Naskh Arabic')

    for line in text.splitlines():
        para = doc.add_paragraph()
        set_rtl(para)
        if not line.strip():
            para.paragraph_format.space_after = Pt(2)
            continue
        run = para.add_run(line)
        run.font.name = 'Noto Naskh Arabic'
        run._element.rPr.rFonts.set(qn('w:cs'), 'Noto Naskh Arabic')
        # Keep the whole paragraph together where possible without forcing
        # entire multi-page documents onto one page.
        para.paragraph_format.widow_control = True

    footer = section.footer.paragraphs[0]
    set_rtl(footer)
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    fr = footer.add_run('پیش‌نویس — نیازمند بررسی و تأیید وکیل')
    fr.font.name = 'Noto Naskh Arabic'
    fr.font.size = Pt(9)
    fr.italic = True

    out = BytesIO()
    doc.save(out)
    return out.getvalue()


def build_case_pdf(result: Dict[str, Any]) -> bytes:
    """Create a searchable PDF by converting the same editable DOCX artifact.

    LibreOffice preserves selectable text, unlike the former page-raster PDF.
    We verify the produced PDF has extractable text and fail closed otherwise.
    """
    import subprocess
    import tempfile
    from pathlib import Path
    import fitz

    docx_bytes = build_case_docx(result)
    with tempfile.TemporaryDirectory(prefix='legalbot_export_') as td:
        root = Path(td)
        docx_path = root / 'LegalBot_Brief.docx'
        docx_path.write_bytes(docx_bytes)
        try:
            subprocess.run(
                ['libreoffice', '-env:UserInstallation=file://' + str(root / 'lo_profile'),
                 '--headless', '--convert-to', 'pdf', '--outdir', str(root), str(docx_path)],
                check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45,
            )
        except FileNotFoundError as exc:
            raise RuntimeError('تبدیل PDF متنی در این محیط در دسترس نیست؛ فایل Word قابل دریافت است.') from exc
        pdf_path = root / 'LegalBot_Brief.pdf'
        if not pdf_path.exists() or pdf_path.stat().st_size < 500:
            raise RuntimeError('تبدیل سند به PDF موفق نبود.')
        pdf_bytes = pdf_path.read_bytes()
        with fitz.open(stream=pdf_bytes, filetype='pdf') as pdf:
            extracted = ''.join(page.get_text() for page in pdf)
            if not extracted.strip() or len(extracted.strip()) < max(10, int(len(_document_text(result.get('draft_text') or '')) * 0.45)):
                raise RuntimeError('PDF ساخته شد اما متن قابل جست‌وجوی کافی ندارد؛ برای جلوگیری از تحویل فایل نامناسب، ارسال متوقف شد.')
        return pdf_bytes


def render_output_overview(result: Dict[str, Any]) -> str:
    """A user-first summary with a clear next action, without implying legal approval."""
    r = result or {}
    if r.get("error"):
        return "❌ آماده‌سازی خروجی انجام نشد.\n" + _clean(r.get("error")) + "\n\nلطفاً دوباره تلاش کنید؛ اگر مشکل ادامه داشت، گزارش فنی را بررسی کنید."
    c = r.get("gate", {}).get("counts", {})
    findings = r.get("findings") or []
    high = int(c.get("high", 0) or 0)
    medium = int(c.get("medium", 0) or 0)
    low = int(c.get("low", 0) or 0)
    status = str(r.get("status") or "BLOCKED").upper()
    lines = [
        "📄 خروجی پیش‌نویس پرونده",
        "",
        ("✅ کنترل ساختاری مانع جدی ثبت نکرده است." if status == "PASS" else "⚠️ این پیش‌نویس هنوز به بررسی بیشتر نیاز دارد."),
        f"موارد نیازمند توجه: جدی {high} · متوسط {medium} · جزئی {low}",
        f"تغییرات ثبت‌شده در نسخه: {len(r.get('changes') or [])}",
        "",
        "پیشنهاد برای ادامه:",
    ]
    if high:
        lines.append("۱. ابتدا موارد جدی را در «گزارش کنترل» بخوانید و اصلاح کنید.")
    elif findings:
        lines.append("۱. موارد فهرست‌شده در «گزارش کنترل» را بررسی کنید.")
    else:
        lines.append("۱. متن پیش‌نویس را با اسناد پرونده و خواستهٔ دقیق تطبیق دهید.")
    lines.append("۲. گزارش تغییرات را مرور کنید تا بدانید چه چیزهایی تغییر کرده است.")
    lines.append("۳. پس از بررسی انسانی، در صورت نیاز فایل Word یا PDF متنی دریافت کنید.")
    lines += [
        "",
        "🔎 کنترل ماشینی، صحت حقوقی یا تأیید مرجع قانونی را تضمین نمی‌کند.",
        "⚖️ پیش از امضا، ثبت یا ارسال، بررسی و تأیید وکیل ضروری است.",
        "🔒 این مرحله فقط خروجی موجود را نمایش می‌دهد و فراخوان تازه‌ای به API نمی‌زند.",
    ]
    if status != "PASS":
        lines += ["", "⛔ تا زمان رسیدگی به هشدارها، از این متن به‌عنوان نسخه نهایی استفاده نکنید."]
    return "\n".join(lines)


def render_case_text(result: Dict[str, Any]) -> str:
    r = result or {}
    if not r.get("draft_text"):
        return "❌ متن ساختاری قابل نمایش نیست."
    prefix = [
        "📄 متن پیش‌نویس بازبینی‌شده",
        "",
        r["draft_text"],
        "",
        "⚖️ این متن نسخه نهایی حقوقی نیست و باید توسط وکیل بررسی و تأیید شود.",
    ]
    if r.get("status") != "PASS":
        prefix.insert(2, "⛔ Gate V159 مسدود است؛ متن زیر فقط برای بررسی داخلی نمایش داده می‌شود.")
    return "\n".join(prefix)


def render_change_report(result: Dict[str, Any], limit: int = 25) -> str:
    changes = result.get("changes") or []
    lines = ["🔍 گزارش تغییرات V158", ""]
    if not changes:
        lines.append("تغییر کنترل‌شده‌ای ثبت نشده است.")
    else:
        for ch in changes[:max(1, limit)]:
            lines += [
                f"• {ch.get('change_id')} — {ch.get('change_type')}",
                f"Finding: {ch.get('finding_id')}",
                f"مسیر: {ch.get('target_path') or ch.get('location')}",
                f"دلیل: {_clean(ch.get('reason')) or '—'}",
                "",
            ]
        if len(changes) > limit:
            lines.append(f"… {len(changes) - limit} تغییر دیگر در Trace ثبت شده است.")
    lines += ["", "⚖️ هر تغییر باید توسط وکیل بررسی شود."]
    return "\n".join(lines)


def render_gate_report(result: Dict[str, Any], limit: int = 20) -> str:
    findings = result.get("findings") or []
    c = result.get("gate", {}).get("counts", {})
    lines = [
        "🧪 گزارش کنترل V159",
        "",
        f"وضعیت: {result.get('status')}",
        f"جدی: {c.get('high', 0)} | متوسط: {c.get('medium', 0)} | پایین: {c.get('low', 0)}",
        "",
    ]
    if not findings:
        lines.append("✅ مورد مسدودکننده‌ای در Gate ثبت نشده است.")
    else:
        for f in findings[:max(1, limit)]:
            lines += [
                f"{str(f.get('severity', 'medium')).upper()} · {f.get('category')}",
                f"مکان: {f.get('location')}",
                f"⚠️ {_clean(f.get('problem'))}",
                f"اقدام: {_clean(f.get('suggested_action')) or 'بررسی دستی'}",
                "",
            ]
    lines += [
        "⚖️ V159 فقط کنترل می‌کند؛ نتیجه Gate تأیید نهایی حقوقی نیست.",
        "🔒 V160 هیچ API خارجی یا موتور حقوقی جدیدی استفاده نمی‌کند.",
    ]
    return "\n".join(lines)


def render_source_report(result: Dict[str, Any], limit: int = 80) -> str:
    trace = result.get("source_trace") or {}
    lines = ["📚 گزارش Trace و منابع", ""]
    if not trace:
        lines.append("Trace در خروجی موجود نیست.")
    else:
        for key, value in trace.items():
            if isinstance(value, list):
                shown = ", ".join(str(x) for x in value[:limit])
                lines.append(f"• {key}: {shown or '—'}")
            elif isinstance(value, dict):
                lines.append(f"• {key}: {len(value)} مورد")
            else:
                lines.append(f"• {key}: {value}")
    lines += ["", "⚖️ برای استناد نهایی، منابع اصلی و وضعیت اعتبار آن‌ها باید توسط وکیل کنترل شوند."]
    return "\n".join(lines)
