# -*- coding: utf-8 -*-
"""Conservative deterministic parser for common Iranian legal document structure.

This is a staging parser, not a legal validator. It preserves source lines and
page provenance, flags ambiguous structures, and never writes to the active bank.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


class LegalStructureError(ValueError):
    pass

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def _norm(value: str) -> str:
    return value.replace("ي", "ی").replace("ك", "ک").replace("ۀ", "ه").replace("ة", "ه").translate(_DIGITS)

_ARTICLE = re.compile(r"^\s*(?:ماده\s*)(?:\(?\s*)([0-9۰-۹٠-٩]+|[الف-ی])(?:\s*\))?\s*(?:[-ـ:：.]\s*)?(.*)$", re.I)
_NOTE = re.compile(r"^\s*(تبصره(?:\s+([0-9۰-۹٠-٩]+))?|تبصره\s+ذیل)\s*[:：ـ-]?\s*(.*)$")
_BAND = re.compile(r"^\s*(?:بند\s+)?(?:\(?\s*)([اآ-ی]+|[0-9۰-۹٠-٩]+)(?:\s*\)|\s*[-ـ:：.])\s*(.*)$")
_SUB = re.compile(r"^\s*(?:جزء\s+)?\(?\s*([0-9۰-۹٠-٩]+|[الف-ی])\s*\)\s*(.*)$")
_DATE = re.compile(r"(?:تاریخ\s*(?:تصویب|ابلاغ|اجرا)?\s*[:：]?\s*)([0-9۰-۹٠-٩]{1,4}[/-][0-9۰-۹٠-٩]{1,2}[/-][0-9۰-۹٠-٩]{1,4})")

@dataclass(frozen=True)
class LegalStructureResult:
    source_sha256: str
    parsed_at: str
    document_type: str
    title: str | None
    issuer: str | None
    dates: dict[str, str]
    preamble: list[dict[str, Any]]
    articles: list[dict[str, Any]]
    trailing_text: list[dict[str, Any]]
    page_count: int
    quality: dict[str, Any]
    review_required: bool = True
    parser_version: str = "3.5.0"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _page_lines(pages: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for page in pages:
        number = int(page.get("page_number", 0) or 0)
        text = str(page.get("text", ""))
        for line_no, line in enumerate(text.replace("\r", "\n").splitlines(), 1):
            clean = line.strip()
            if clean:
                rows.append({"page_number": number, "line_number": line_no, "text": clean})
    return rows


def parse_legal_structure(pages: list[dict[str, Any]], *, source_sha256: str = "",
                          document_type: str = "unknown") -> LegalStructureResult:
    """Parse page-preserving text (from extractor or OCR) into tentative legal units."""
    if not isinstance(pages, list) or not pages:
        raise LegalStructureError("صفحات ورودی برای تحلیل ساختار وجود ندارد")
    rows = _page_lines(pages)
    if not rows:
        raise LegalStructureError("متن قابل تحلیل در صفحات ورودی وجود ندارد")

    title: str | None = None
    issuer: str | None = None
    dates: dict[str, str] = {}
    for row in rows[: min(len(rows), 35)]:
        line = _norm(row["text"])
        if title is None and any(k in line for k in ("قانون", "آیین نامه", "تصویب نامه", "دستورالعمل", "بخشنامه")) and len(line) <= 220:
            title = row["text"]
        if issuer is None and any(k in line for k in ("مجلس شورای اسلامی", "هیئت وزیران", "هیات وزیران", "قوه قضائیه", "وزارت")):
            issuer = row["text"]
        match = _DATE.search(line)
        if match:
            key = "approval_or_issue_date" if "تصویب" in line else "date"
            dates.setdefault(key, match.group(1))

    preamble: list[dict[str, Any]] = []
    trailing: list[dict[str, Any]] = []
    articles: list[dict[str, Any]] = []
    current_article: dict[str, Any] | None = None
    current_note: dict[str, Any] | None = None
    article_lines = 0
    recognized_notes = 0
    recognized_bands = 0
    recognized_subs = 0
    seen_article = False

    def append_text(target: dict[str, Any], row: dict[str, Any]) -> None:
        target.setdefault("text_lines", []).append({"page_number": row["page_number"], "line_number": row["line_number"], "text": row["text"]})

    for row in rows:
        raw = row["text"]
        line = _norm(raw)
        am = _ARTICLE.match(line)
        if am and (len(am.group(1)) <= 3):
            seen_article = True
            current_note = None
            current_article = {"number": am.group(1), "heading": am.group(2).strip(), "start_page": row["page_number"], "end_page": row["page_number"], "text_lines": [], "notes": [], "bands": []}
            articles.append(current_article)
            article_lines += 1
            if am.group(2).strip():
                append_text(current_article, {**row, "text": am.group(2).strip()})
            continue
        if not seen_article:
            preamble.append(dict(row))
            continue
        if current_article is None:
            trailing.append(dict(row))
            continue
        current_article["end_page"] = row["page_number"]
        nm = _NOTE.match(line)
        if nm:
            note = {"label": nm.group(1), "number": nm.group(2), "text_lines": []}
            current_article["notes"].append(note)
            current_note = note
            recognized_notes += 1
            if nm.group(3).strip():
                append_text(note, {**row, "text": nm.group(3).strip()})
            continue
        bm = _BAND.match(line)
        if bm and bm.group(2).strip():
            band = {"label": bm.group(1), "text_lines": []}
            current_article["bands"].append(band)
            current_note = None
            append_text(band, {**row, "text": bm.group(2).strip()})
            recognized_bands += 1
            continue
        sm = _SUB.match(line)
        if sm and current_article["bands"] and sm.group(2).strip():
            band = current_article["bands"][-1]
            band.setdefault("subitems", []).append({"label": sm.group(1), "text_lines": [{"page_number": row["page_number"], "line_number": row["line_number"], "text": sm.group(2).strip()}]})
            recognized_subs += 1
            current_note = None
            continue
        if current_note is not None:
            append_text(current_note, row)
        else:
            append_text(current_article, row)

    article_numbers = [a["number"] for a in articles]
    duplicates = sorted({n for n in article_numbers if article_numbers.count(n) > 1})
    numeric = [int(n) for n in article_numbers if n.isdigit()]
    non_increasing = any(b <= a for a, b in zip(numeric, numeric[1:]))
    quality = {
        "recognized_article_count": len(articles),
        "recognized_note_count": recognized_notes,
        "recognized_band_count": recognized_bands,
        "recognized_subitem_count": recognized_subs,
        "duplicate_article_numbers": duplicates,
        "article_number_order_warning": non_increasing,
        "classification": "structured_candidate" if articles else "unstructured_or_unrecognized",
        "warnings": [],
        "disclaimer": "تشخیص ساختار قطعی نیست؛ متن‌های مبهم و شماره‌گذاری باید با PDF اصلی بازبینی شوند.",
    }
    if not articles:
        quality["warnings"].append("هیچ ماده‌ای با الگوهای شناخته‌شده شناسایی نشد")
    if duplicates:
        quality["warnings"].append("شماره ماده تکراری شناسایی شد")
    if non_increasing:
        quality["warnings"].append("ترتیب شماره مواد ممکن است نامنظم باشد")
    if not title:
        quality["warnings"].append("عنوان سند با اطمینان شناسایی نشد")
    return LegalStructureResult(
        source_sha256=source_sha256, parsed_at=datetime.now(timezone.utc).isoformat(),
        document_type=document_type, title=title, issuer=issuer, dates=dates,
        preamble=preamble, articles=articles, trailing_text=trailing,
        page_count=max(int(p.get("page_number", 0) or 0) for p in pages), quality=quality,
    )


def write_legal_structure_json(result: LegalStructureResult, output_path: str | Path) -> Path:
    """Atomically write parser output as a staging sidecar JSON."""
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(result.to_dict(), stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, target)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return target
