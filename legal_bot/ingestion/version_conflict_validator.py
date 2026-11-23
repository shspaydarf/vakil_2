# -*- coding: utf-8 -*-
"""Conservative duplicate and version-difference screening for legal documents.

This module detects candidate duplicates and textual differences. It does not
make legal findings about amendment, repeal, validity, or effective dates.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def _norm(value: Any) -> str:
    text = str(value or "").translate(_DIGITS)
    text = text.replace("ي", "ی").replace("ك", "ک")
    return re.sub(r"\s+", " ", text).strip().casefold()


def _first(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return value
    return None


def _metadata(doc: dict[str, Any]) -> dict[str, Any]:
    value = doc.get("metadata") or doc.get("document_metadata") or {}
    return value if isinstance(value, dict) else {}


def _structure(doc: dict[str, Any]) -> dict[str, Any]:
    value = doc.get("structure") or doc.get("legal_structure") or {}
    if not value and isinstance(doc.get("staging_document"), dict):
        value = doc["staging_document"].get("legal_structure") or doc["staging_document"].get("structure") or {}
    return value if isinstance(value, dict) else {}


def _articles(doc: dict[str, Any]) -> dict[str, str]:
    structure = _structure(doc)
    rows = structure.get("articles") or doc.get("articles") or []
    result: dict[str, str] = {}
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            number = _norm(_first(row, "number", "article_number", " ماده"))
            body = _norm(_first(row, "text", "content", "body"))
            if number:
                # Preserve repeated article numbers as explicit collision markers.
                result[number] = (result[number] + "\n[duplicate-entry]\n" if number in result else "") + body
    return result


def _full_text(doc: dict[str, Any]) -> str:
    for key in ("normalized_text", "text", "full_text"):
        value = doc.get(key)
        if isinstance(value, str) and value.strip():
            return _norm(value)
        if isinstance(value, dict):
            candidate = value.get("text") or value.get("normalized_text")
            if isinstance(candidate, str) and candidate.strip():
                return _norm(candidate)
    articles = _articles(doc)
    return "\n".join(f"ماده {n} {t}" for n, t in sorted(articles.items()))


def _identity(doc: dict[str, Any]) -> tuple[str, str, str, str]:
    meta = _metadata(doc)
    return (
        _norm(_first(meta, "document_type", "doc_type", "type") or _first(doc, "document_type", "doc_type")),
        _norm(_first(meta, "title", "document_title") or _first(doc, "title", "document_title")),
        _norm(_first(meta, "issuer", "issuing_authority", "authority") or _first(doc, "issuer", "authority")),
        _norm(_first(meta, "number", "document_number", "registration_number") or _first(doc, "number", "document_number")),
    )


def _sha(text: str) -> str | None:
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if text else None


@dataclass(frozen=True)
class VersionConflictReport:
    checked_at: str
    validator_version: str
    status: str
    documents_checked: int
    comparisons: list[dict[str, Any]]
    findings: list[dict[str, Any]]
    review_required: bool = True
    legal_amendment_proven: bool = False
    repeal_proven: bool = False
    active_bank_changed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compare_legal_document_versions(
    documents: list[dict[str, Any]], *, near_duplicate_threshold: float = 0.94,
) -> VersionConflictReport:
    """Compare staged documents; all detected relationships remain candidates.

    A strong identity match requires at least title plus one of issuer/number/type.
    Near-duplicate matching uses text similarity only and is never an auto-merge.
    """
    if not isinstance(documents, list):
        raise ValueError("ورودی اسناد باید فهرست باشد")
    if not 0.5 <= near_duplicate_threshold <= 1.0:
        raise ValueError("آستانه شباهت باید بین ۰٫۵ و ۱ باشد")
    prepared = []
    for index, doc in enumerate(documents):
        if not isinstance(doc, dict):
            continue
        text = _full_text(doc)
        articles = _articles(doc)
        prepared.append({
            "index": index,
            "id": str(doc.get("document_id") or doc.get("id") or f"document_{index + 1}"),
            "identity": _identity(doc),
            "text": text,
            "sha256": _sha(text),
            "articles": articles,
            "date": _norm(_first(_metadata(doc), "date", "approval_date", "promulgation_date")),
        })

    comparisons: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    for left_pos in range(len(prepared)):
        for right_pos in range(left_pos + 1, len(prepared)):
            a, b = prepared[left_pos], prepared[right_pos]
            if not a["text"] or not b["text"]:
                continue
            similarity = SequenceMatcher(None, a["text"], b["text"], autojunk=False).ratio()
            same_identity = (
                bool(a["identity"][1]) and a["identity"][1] == b["identity"][1]
                and sum(bool(x) for x in a["identity"][0::1] if x) >= 2
                and all(not x or not y or x == y for x, y in zip(a["identity"], b["identity"]))
            )
            if a["sha256"] == b["sha256"]:
                kind = "exact_duplicate_candidate"
            elif same_identity:
                kind = "same_identity_different_text_candidate"
            elif similarity >= near_duplicate_threshold:
                kind = "near_duplicate_candidate"
            else:
                continue

            article_a, article_b = a["articles"], b["articles"]
            added = sorted(set(article_b) - set(article_a))
            removed = sorted(set(article_a) - set(article_b))
            changed = []
            for number in sorted(set(article_a) & set(article_b)):
                ratio = SequenceMatcher(None, article_a[number], article_b[number], autojunk=False).ratio()
                if ratio < 0.995:
                    changed.append({"article_number": number, "similarity": round(ratio, 4)})
            comparison = {
                "document_a": a["id"], "document_b": b["id"], "relationship": kind,
                "text_similarity": round(similarity, 4), "identity_fields": {
                    "document_type": bool(a["identity"][0] and a["identity"][0] == b["identity"][0]),
                    "title": bool(a["identity"][1] and a["identity"][1] == b["identity"][1]),
                    "issuer": bool(a["identity"][2] and a["identity"][2] == b["identity"][2]),
                    "number": bool(a["identity"][3] and a["identity"][3] == b["identity"][3]),
                },
                "dates": {"a": a["date"] or None, "b": b["date"] or None},
                "article_differences": {"only_in_b": added, "only_in_a": removed, "changed": changed},
                "sha256": {"a": a["sha256"], "b": b["sha256"]},
                "legal_effect": "undetermined_requires_human_review",
            }
            comparisons.append(comparison)
            severity = "medium" if kind == "exact_duplicate_candidate" else "high"
            findings.append({"code": kind, "severity": severity,
                             "documents": [a["id"], b["id"]],
                             "note": "شباهت یا تفاوت متنی به‌تنهایی اصلاح، نسخ یا اعتبار حقوقی را اثبات نمی‌کند."})

    status = "no_candidate_relationship_detected" if not findings else "review_required"
    return VersionConflictReport(
        checked_at=datetime.now(timezone.utc).isoformat(), validator_version="4.4.0",
        status=status, documents_checked=len(prepared), comparisons=comparisons, findings=findings,
    )


def write_version_conflict_report(report: VersionConflictReport, output_path: str | Path) -> Path:
    """Atomically write a standalone JSON report."""
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report.to_dict(), ensure_ascii=False, indent=2)
    fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, target)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
    return target
