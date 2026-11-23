"""Readable, paginated PDF export for AI contract-playbook reports."""
from __future__ import annotations

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT, TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, KeepTogether, HRFlowable

INK = colors.HexColor("#202938")
NAVY = colors.HexColor("#17365D")
MUTED = colors.HexColor("#657286")
LINE = colors.HexColor("#D8DEE8")


def _register_font() -> str:
    candidates = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    )
    for path in candidates:
        try:
            if "MachinaUnicode" not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont("MachinaUnicode", path))
            return "MachinaUnicode"
        except (OSError, ValueError):
            continue
    return "Helvetica"


def _rtl(text: str) -> str:
    """Shape Persian/Arabic text when optional shaping libraries are installed."""
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(text))
    except ImportError:
        return text


def _page_chrome(canvas, doc, title: str, font: str) -> None:
    canvas.saveState()
    width, height = A4
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.6)
    canvas.line(18 * mm, height - 13 * mm, width - 18 * mm, height - 13 * mm)
    canvas.setFont(font, 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, height - 10.5 * mm, "MACHINA | CONTRACT REVIEW")
    canvas.drawRightString(width - 18 * mm, 9 * mm, f"{doc.page}")
    canvas.line(18 * mm, 14 * mm, width - 18 * mm, 14 * mm)
    canvas.restoreState()


def build_contract_report_pdf(report: str, playbook_title: str = "بررسی قرارداد") -> BytesIO:
    """Build an in-memory A4 report with clear hierarchy and page numbering."""
    text = str(report or "").strip()
    if not text:
        raise ValueError("گزارش خالی است و امکان ساخت PDF وجود ندارد")

    font = _register_font()
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, rightMargin=19 * mm, leftMargin=19 * mm,
        topMargin=21 * mm, bottomMargin=21 * mm,
        title=f"MACHINA - {playbook_title}", author="MACHINA",
        subject="گزارش بررسی اولیه قرارداد بر اساس Playbook",
    )
    base = getSampleStyleSheet()["BodyText"]
    body = ParagraphStyle("MachinaBody", parent=base, fontName=font, fontSize=9,
        leading=15, alignment=TA_RIGHT, textColor=INK, spaceAfter=5, wordWrap="RTL")
    title_style = ParagraphStyle("MachinaTitle", parent=body, fontSize=17,
        leading=24, textColor=NAVY, spaceAfter=7)
    subtitle = ParagraphStyle("MachinaSubtitle", parent=body, fontSize=8,
        leading=12, textColor=MUTED, spaceAfter=10)
    section = ParagraphStyle("MachinaSection", parent=body, fontSize=11,
        leading=17, textColor=NAVY, spaceBefore=7, spaceAfter=5)
    story = [
        Paragraph(escape(_rtl("MACHINA | " + playbook_title)), title_style),
        Paragraph(escape(_rtl("گزارش بررسی اولیه قرارداد — نیازمند بازبینی وکیل")), subtitle),
        HRFlowable(width="100%", thickness=1, color=LINE, spaceAfter=8),
    ]

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            story.append(Spacer(1, 2 * mm))
            continue
        # Recognize common report headings without changing the report's meaning.
        clean = line.lstrip("# ").strip()
        is_heading = line.startswith("#") or (len(clean) < 85 and clean.endswith(":") and not clean.startswith(("-", "•")))
        style = section if is_heading else body
        if line.startswith(("- ", "• ", "* ")):
            clean = "•  " + clean[2:].strip()
        story.append(Paragraph(escape(_rtl(clean)).replace("  ", " &nbsp; "), style))

    def decorate(canvas, current_doc):
        _page_chrome(canvas, current_doc, playbook_title, font)

    doc.build(story, onFirstPage=decorate, onLaterPages=decorate)
    buffer.seek(0)
    return buffer
