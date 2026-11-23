# -*- coding: utf-8 -*-
"""Conservative Persian legal-text normalization for staged ingestion.

Original text is always retained verbatim. Normalization is deterministic,
traceable, and deliberately avoids deleting headers, footers, numbers or legal
content. This module never writes to the active legal JSON bank.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Canonical display digits are Persian. Both Arabic-Indic and ASCII digits are
# converted, while the original source remains available in raw_text.
_DIGIT_MAP = str.maketrans("0123456789٠١٢٣٤٥٦٧٨٩", "۰۱۲۳۴۵۶۷۸۹۰۱۲۳۴۵۶۷۸۹")
_CHAR_MAP = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "ۀ": "ه", "ة": "ه"})

@dataclass(frozen=True)
class NormalizationPolicy:
    normalize_digits_to_persian: bool = True
    normalize_arabic_characters: bool = True
    normalize_whitespace: bool = True
    normalize_zwnj: bool = True
    collapse_repeated_punctuation: bool = False
    min_nonspace_chars_for_quality: int = 20

@dataclass(frozen=True)
class NormalizedPage:
    page_number: int
    raw_text: str
    normalized_text: str
    raw_sha256: str
    normalized_sha256: str
    change_count: int
    quality: str
    provenance: str

@dataclass(frozen=True)
class LegalTextNormalizationResult:
    source_sha256: str
    normalized_at: str
    policy: dict[str, Any]
    pages: list[dict[str, Any]]
    document_text: str
    quality: dict[str, Any]
    review_required: bool = True
    normalizer_version: str = "3.6.0"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_persian_text(text: str, *, policy: NormalizationPolicy | None = None) -> str:
    """Normalize typography only; do not rewrite or remove legal wording."""
    policy = policy or NormalizationPolicy()
    value = str(text)
    if policy.normalize_arabic_characters:
        value = value.translate(_CHAR_MAP)
    if policy.normalize_digits_to_persian:
        value = value.translate(_DIGIT_MAP)
    # Remove invisible directional controls that can corrupt search/display;
    # retain ZWNJ because it is meaningful in Persian orthography.
    value = re.sub(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069]", "", value)
    if policy.normalize_zwnj:
        value = value.replace("\u200c\u200c", "\u200c")
        value = re.sub(r"[ \t]*\u200c[ \t]*", "\u200c", value)
    if policy.normalize_whitespace:
        value = value.replace("\u00a0", " ").replace("\u202f", " ")
        value = re.sub(r"[ \t]+", " ", value)
        value = re.sub(r" *\n *", "\n", value)
        value = re.sub(r"\n{3,}", "\n\n", value)
        value = value.strip()
    if policy.collapse_repeated_punctuation:
        # Opt-in only: avoid changing legal ellipses or meaningful punctuation by default.
        value = re.sub(r"([،؛,:：])\1+", r"\1", value)
    return value


def normalize_legal_document(pages: list[dict[str, Any]], *, source_sha256: str = "",
                             policy: NormalizationPolicy | None = None,
                             structure: dict[str, Any] | None = None) -> LegalTextNormalizationResult:
    """Normalize page text and optionally parsed structure while retaining raw text."""
    if not isinstance(pages, list) or not pages:
        raise ValueError("صفحات ورودی برای استانداردسازی وجود ندارد")
    policy = policy or NormalizationPolicy()
    results: list[dict[str, Any]] = []
    normalized_parts: list[str] = []
    total_changes = 0
    for index, page in enumerate(pages, 1):
        page_no = int(page.get("page_number", index) or index)
        raw = str(page.get("text", ""))
        normalized = normalize_persian_text(raw, policy=policy)
        changes = sum(1 for a, b in zip(raw, normalized) if a != b) + abs(len(raw) - len(normalized))
        # The count is a conservative character-difference indicator, not an edit log.
        quality = "text_present" if len(re.sub(r"\s", "", normalized)) >= policy.min_nonspace_chars_for_quality else "sparse_or_empty"
        item = NormalizedPage(
            page_number=page_no, raw_text=raw, normalized_text=normalized,
            raw_sha256=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            normalized_sha256=hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
            change_count=changes, quality=quality,
            provenance=str(page.get("provenance", page.get("source", "pdf_text_or_ocr_unspecified"))),
        )
        results.append(asdict(item))
        normalized_parts.append(normalized)
        total_changes += changes

    normalized_structure = None
    if structure is not None:
        normalized_structure = copy.deepcopy(structure)
        def visit(node: Any) -> None:
            if isinstance(node, dict):
                for key, value in list(node.items()):
                    if key in {"text", "heading", "title", "label"} and isinstance(value, str):
                        node[key] = normalize_persian_text(value, policy=policy)
                    else:
                        visit(value)
            elif isinstance(node, list):
                for child in node:
                    visit(child)
        visit(normalized_structure)

    output_pages = results
    quality_report = {
        "page_count": len(results),
        "sparse_page_numbers": [p["page_number"] for p in results if p["quality"] == "sparse_or_empty"],
        "changed_page_count": sum(1 for p in results if p["raw_text"] != p["normalized_text"]),
        "character_change_indicator": total_changes,
        "normalization_is_lossless": True,
        "structure_normalized": normalized_structure is not None,
        "warnings": ["استانداردسازی صرفاً نگارشی است؛ محتوای حقوقی و صحت OCR را تأیید نمی‌کند."],
    }
    if normalized_structure is not None:
        quality_report["normalized_structure"] = normalized_structure
    return LegalTextNormalizationResult(
        source_sha256=source_sha256, normalized_at=datetime.now(timezone.utc).isoformat(),
        policy=asdict(policy), pages=output_pages,
        document_text="\n\n".join(normalized_parts), quality=quality_report,
    )


def write_normalization_json(result: LegalTextNormalizationResult, output_path: str | Path) -> Path:
    """Atomically write a separate staging sidecar JSON."""
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
