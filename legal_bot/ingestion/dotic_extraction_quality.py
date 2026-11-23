# -*- coding: utf-8 -*-
"""Phase 10.4.8: non-destructive quality checks for Persian legal PDF extraction.

This module flags suspicious text; it never silently normalizes or edits source text.
No network access and no active-bank writes.
"""
from __future__ import annotations
import argparse, hashlib, json, re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

class ExtractionQualityError(ValueError):
    pass

_DIGIT_RE = re.compile(r"[0-9۰-۹٠-٩]+")
_ARTICLE_RE = re.compile(r"(?:ماده\s*[0-9۰-۹٠-٩]+|تبصره\s*[0-9۰-۹٠-٩]*)")
_SECTION_RE = re.compile(r"(?:فصل|بخش|باب|مقدمه|پیوست|ضمیمه)")
_TABLE_RE = re.compile(r"(?:\t|\|{1,}|_{3,}|-{3,}|\s{4,}\S+\s{4,}\S+)")

def _page_quality(text: str) -> dict[str, Any]:
    chars = len(text)
    replacement = text.count("\ufffd")
    controls = sum(1 for c in text if ord(c) in (0x200e, 0x200f, 0x202a, 0x202b, 0x202c, 0x202d, 0x202e, 0x2066, 0x2067, 0x2068, 0x2069))
    persian = sum(1 for c in text if '\u0600' <= c <= '\u06ff')
    tokens = _DIGIT_RE.findall(text)
    mixed_digit_tokens = [t for t in tokens if any('0' <= c <= '9' for c in t) and any('۰' <= c <= '۹' or '٠' <= c <= '٩' for c in t)]
    flags = []
    if not text.strip(): flags.append("empty_page_text")
    if replacement: flags.append("unicode_replacement_characters")
    if controls: flags.append("bidirectional_control_characters_present")
    if mixed_digit_tokens: flags.append("mixed_digit_scripts_in_token")
    if chars and persian == 0: flags.append("no_persian_arabic_script_detected")
    score = 100
    if not text.strip(): score -= 60
    score -= min(40, replacement * 8)
    score -= min(20, controls * 2)
    score -= min(20, len(mixed_digit_tokens) * 5)
    score = max(0, score)
    return {"character_count": chars, "persian_arabic_script_characters": persian,
            "replacement_character_count": replacement, "bidi_control_count": controls,
            "digit_tokens": len(tokens), "mixed_digit_script_tokens": mixed_digit_tokens,
            "quality_score": score, "flags": flags}

def analyze_extraction(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict) or data.get("phase") != "10.4.7":
        raise ExtractionQualityError("خروجی معتبر فاز ۱۰.۴.۷ لازم است")
    if data.get("active_bank_write") is not False:
        raise ExtractionQualityError("خروجی استخراج وضعیت نوشتن بانک فعال را ایمن اعلام نکرده است")
    pages = data.get("pages")
    if not isinstance(pages, list): raise ExtractionQualityError("فهرست صفحات استخراج‌شده معتبر نیست")
    seen, page_reports, texts = set(), [], []
    for row in pages:
        if not isinstance(row, dict) or not isinstance(row.get("page_number"), int):
            raise ExtractionQualityError("ساختار صفحه نامعتبر است")
        number = row["page_number"]
        if number in seen: raise ExtractionQualityError("شماره صفحه تکراری است")
        seen.add(number)
        text = str(row.get("selected_text", ""))
        texts.append(text)
        q = _page_quality(text)
        q.update({"page_number": number,
                  "native_ocr_disagreement": bool(row.get("native_text") and row.get("ocr_text") and row.get("native_text") != row.get("ocr_text")),
                  "ocr_review_required": bool(row.get("ocr_text")) or bool(row.get("likely_scanned_or_text_sparse"))})
        page_reports.append(q)
    ordered = sorted(seen)
    missing = sorted(set(range(1, max(ordered, default=0) + 1)) - seen)
    duplicates = []
    by_hash = {}
    for row in pages:
        text = str(row.get("selected_text", "")).strip()
        if text:
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if digest in by_hash: duplicates.append({"page_number": row["page_number"], "matches_page": by_hash[digest]})
            else: by_hash[digest] = row["page_number"]
    full = "\n".join(texts)
    articles = [{"label": m.group(0), "offset": m.start()} for m in _ARTICLE_RE.finditer(full)]
    sections = [{"label": m.group(0), "offset": m.start()} for m in _SECTION_RE.finditer(full)]
    table_pages = [row["page_number"] for row in pages if _TABLE_RE.search(str(row.get("selected_text", "")))]
    avg = round(sum(p["quality_score"] for p in page_reports) / len(page_reports), 2) if page_reports else 0
    flagged = [p["page_number"] for p in page_reports if p["flags"] or p["native_ocr_disagreement"] or p["ocr_review_required"]]
    complete = bool(data.get("complete"))
    return {"phase": "10.4.8", "source_pdf_sha256": data.get("source_pdf_sha256"),
            "pages_reviewed": len(page_reports), "extraction_complete": complete,
            "missing_page_numbers_within_extracted_range": missing,
            "duplicate_text_pages": duplicates, "page_quality": page_reports,
            "average_page_quality_score": avg, "flagged_pages": sorted(set(flagged)),
            "article_and_paragraph_markers": articles, "section_markers": sections,
            "possible_table_pages": table_pages,
            "review_required": bool(flagged or missing or duplicates or not complete),
            "text_modified": False, "source_text_preserved": True,
            "legal_authenticity_verified": False, "legal_status_verified": False,
            "active_bank_write": False, "decision": "quarantine_quality_report_only_human_review_required",
            "analyzed_at": datetime.now(timezone.utc).isoformat()}

def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Non-destructive quality analysis of extracted Dotic PDF text")
    p.add_argument("--input", required=True); p.add_argument("--output")
    a = p.parse_args(argv)
    try: source = json.loads(Path(a.input).read_text(encoding="utf-8"))
    except Exception as exc: raise ExtractionQualityError("فایل خروجی استخراج قابل خواندن نیست") from exc
    report = analyze_extraction(source)
    out = Path(a.output) if a.output else Path(a.input).with_name(Path(a.input).stem + ".quality.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(out), "pages_reviewed": report["pages_reviewed"], "review_required": report["review_required"]}, ensure_ascii=False))
    return 0
if __name__ == "__main__": raise SystemExit(main())
