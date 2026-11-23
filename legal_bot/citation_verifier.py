# -*- coding: utf-8 -*-
"""Conservative, local-first citation traceability checks for Persian legal drafts.

This module does not browse the web or certify the legal validity of a citation.
It only compares citation mentions against the project's source registry and
reports the registry's recorded verification status.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict

from .config import DATA_DIR

_REGISTRY_PATH = Path(DATA_DIR) / "iran" / "official_sources.json"
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_VERIFIED = {"verified", "verified_current", "verified_current_source_backed"}


def _norm(value: Any) -> str:
    s = str(value or "").replace("ي", "ی").replace("ك", "ک").replace("‌", " ")
    return re.sub(r"\s+", " ", s).strip().casefold()


def _registry() -> Dict[str, Any]:
    try:
        with _REGISTRY_PATH.open(encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def audit_citations(text: str) -> Dict[str, Any]:
    """Identify explicit article/principle references and map them to registry entries.

    A registry title match is not proof that the cited article exists or that the
    quoted rule is current. Exact article-level verification remains manual.
    """
    body = str(text or "")
    registry = _registry()
    laws = registry.get("laws") or []
    authorities = {str(x.get("id")): x for x in (registry.get("authorities") or []) if isinstance(x, dict)}
    mentions = []
    # Capture compact citation windows around article/principle numbers.
    pattern = re.compile(r"(?:ماده|مواد|اصل)\s*([۰-۹٠-٩0-9]+(?:\s*(?:تا|الی|و|،|-)\s*[۰-۹٠-٩0-9]+)*)", re.I)
    for match in pattern.finditer(body):
        start, end = max(0, match.start() - 100), min(len(body), match.end() + 100)
        context = body[start:end]
        norm_context = _norm(context)
        candidates = []
        for law in laws:
            title = str(law.get("title") or "").strip()
            if title and _norm(title) in norm_context:
                candidates.append(law)
        # Prefer the closest title in the local context, but keep ambiguity visible.
        unique = {str(x.get("title")): x for x in candidates}
        if len(unique) == 1:
            law = next(iter(unique.values()))
            status = str(law.get("status") or "unknown")
            primary_ids = law.get("primary_sources") or []
            source_links = [authorities[x].get("url") for x in primary_ids if x in authorities and authorities[x].get("url")]
            if status in _VERIFIED:
                level = "registry_verified_text_status"
                label = "وضعیت متن در فهرست پروژه تأییدشده ثبت شده؛ تطبیق شماره ماده و نسخه جاری همچنان لازم است"
            elif status == "user_pdf_active":
                level = "user_document_not_independently_verified"
                label = "متن از PDF کاربر؛ تطبیق مستقل با نسخه رسمی ثبت نشده"
            elif status == "user_pdf_historical":
                level = "historical_text_warning"
                label = "نسخه تاریخی؛ برای استناد جاری کافی نیست"
            elif status == "source_verified_text_pending":
                level = "source_known_text_pending"
                label = "منبع شناخته‌شده است اما متن محلی تأیید نشده"
            else:
                level = "manual_verification_required"
                label = "تطبیق متن و اعتبار جاری لازم است"
            mentions.append({
                "reference": match.group(0), "law_title": law.get("title"),
                "registry_status": status, "verification_level": level,
                "label": label, "source_urls": source_links,
                "context": re.sub(r"\s+", " ", context).strip(),
            })
        else:
            mentions.append({
                "reference": match.group(0), "law_title": None,
                "registry_status": "ambiguous_or_not_found",
                "verification_level": "manual_verification_required",
                "label": "عنوان قانون در محدوده استناد به‌طور یکتا در فهرست پروژه پیدا نشد؛ عنوان دقیق و منبع رسمی را مشخص کنید",
                "source_urls": [], "context": re.sub(r"\s+", " ", context).strip(),
            })
    return {
        "version": 1,
        "registry_last_reviewed": registry.get("last_reviewed"),
        "mentions": mentions,
        "count": len(mentions),
        "verified_status_count": sum(x["verification_level"] == "registry_verified_text_status" for x in mentions),
        "manual_review_count": sum(x["verification_level"] != "registry_verified_text_status" for x in mentions),
        "legal_validity_certified": False,
        "api_used": False,
    }


def render_citation_audit(text: str) -> str:
    report = audit_citations(text)
    lines = ["📚 گزارش راستی‌آزمایی مقدماتی استنادها", ""]
    if not report["mentions"]:
        lines.append("استناد شماره‌دار از نوع ماده/اصل شناسایی نشد؛ این موضوع به معنای نبود استناد درستی نیست.")
    for i, item in enumerate(report["mentions"], 1):
        lines.append(f"{i}. {item['reference']} — {item['label']}")
        if item.get("law_title"):
            lines.append(f"   عنوان تطبیق‌یافته: {item['law_title']}")
        if item.get("source_urls"):
            lines.append("   منابع ثبت‌شده: " + "؛ ".join(item["source_urls"]))
    lines += ["", f"تاریخ آخرین بازبینی فهرست منابع پروژه: {report.get('registry_last_reviewed') or 'ثبت نشده'}.",
              "این ابزار فقط وضعیت فراداده فهرست محلی را گزارش می‌کند؛ وجود ماده، متن دقیق، اصلاحات بعدی، نسخ و قابلیت اعمال در پرونده را به‌طور خودکار تأیید نمی‌کند.",
              "برای استناد نهایی، متن و وضعیت اعتبار را در منبع رسمی صادرکننده/منتشرکننده کنترل کنید."]
    return "\n".join(lines)
