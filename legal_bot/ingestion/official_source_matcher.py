# -*- coding: utf-8 -*-
"""Conservative cross-source matching for staged legal documents.

This module compares supplied source records; it does not fetch the web or
assert legal validity. A secondary publication can corroborate discovery but
cannot be reported as official confirmation.
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
from urllib.parse import urlparse

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def _norm(value: Any) -> str:
    text = str(value or "").translate(_DIGITS).replace("ي", "ی").replace("ك", "ک")
    return re.sub(r"\s+", " ", text).strip().casefold()


def _first(obj: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = obj.get(key)
        if value not in (None, ""):
            return value
    return None


def _meta(doc: dict[str, Any]) -> dict[str, Any]:
    value = doc.get("metadata") or doc.get("document_metadata") or {}
    return value if isinstance(value, dict) else {}


def _text(doc: dict[str, Any]) -> str:
    for key in ("normalized_text", "full_text", "text"):
        value = doc.get(key)
        if isinstance(value, str) and value.strip():
            return _norm(value)
        if isinstance(value, dict):
            nested = value.get("text") or value.get("normalized_text")
            if isinstance(nested, str) and nested.strip():
                return _norm(nested)
    rows = doc.get("articles") or (doc.get("structure") or {}).get("articles") or []
    if isinstance(rows, list):
        return "\n".join(_norm((r.get("number", "") + " " + str(r.get("text", "")))) for r in rows if isinstance(r, dict))
    return ""


def _identity(doc: dict[str, Any]) -> dict[str, str]:
    meta = _meta(doc)
    return {
        "title": _norm(_first(meta, "title", "document_title") or _first(doc, "title", "document_title")),
        "document_type": _norm(_first(meta, "document_type", "doc_type", "type") or _first(doc, "document_type", "doc_type")),
        "issuer": _norm(_first(meta, "issuer", "issuing_authority", "authority") or _first(doc, "issuer", "authority")),
        "number": _norm(_first(meta, "number", "document_number", "registration_number") or _first(doc, "number", "document_number")),
        "approval_date": _norm(_first(meta, "approval_date", "date") or _first(doc, "approval_date", "date")),
        "publication_date": _norm(_first(meta, "publication_date", "published_at") or _first(doc, "publication_date")),
    }


def _sha(text: str) -> str | None:
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if text else None


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower().rstrip(".")
    except Exception:
        return ""


def _source_role(record: dict[str, Any], catalog: dict[str, Any] | None) -> str:
    source_id = str(record.get("source_id") or "")
    if catalog:
        for row in catalog.get("sources", []):
            if row.get("source_id") == source_id:
                return str(row.get("source_role") or record.get("source_role") or "unknown")
    return str(record.get("source_role") or "unknown")


@dataclass(frozen=True)
class SourceMatchReport:
    checked_at: str
    validator_version: str
    document_id: str
    status: str
    source_comparisons: list[dict[str, Any]]
    findings: list[dict[str, Any]]
    official_confirmation: bool = False
    live_source_access_performed: bool = False
    legal_validity_proven: bool = False
    active_bank_changed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def match_document_against_sources(
    document: dict[str, Any], source_records: list[dict[str, Any]], *,
    source_catalog: dict[str, Any] | None = None,
    exact_text_threshold: float = 0.995,
    close_text_threshold: float = 0.90,
) -> SourceMatchReport:
    """Compare a staged document with supplied source-page/source-text records.

    Source records may be CandidateDocument dictionaries enriched with source
    metadata and text. This is deliberately offline: no URL is fetched.
    """
    if not isinstance(document, dict) or not isinstance(source_records, list):
        raise ValueError("سند و فهرست سوابق منبع باید ساختار معتبر داشته باشند")
    if not (0.5 <= close_text_threshold <= exact_text_threshold <= 1.0):
        raise ValueError("آستانه‌های تطبیق متن معتبر نیستند")
    doc_id = str(document.get("document_id") or document.get("id") or "staged_document")
    target_id, target_text = _identity(document), _text(document)
    comparisons: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    official_match = False

    for index, record in enumerate(source_records):
        if not isinstance(record, dict):
            continue
        source_id = str(record.get("source_id") or "unknown")
        role = _source_role(record, source_catalog)
        source_identity = _identity(record)
        source_text = _text(record)
        identity_matches = {key: bool(target_id[key] and source_identity[key] and target_id[key] == source_identity[key])
                            for key in target_id}
        identity_conflicts = [key for key in ("title", "document_type", "issuer", "number", "approval_date")
                              if target_id[key] and source_identity[key] and target_id[key] != source_identity[key]]
        similarity = SequenceMatcher(None, target_text, source_text, autojunk=False).ratio() if target_text and source_text else None
        exact_text = bool(target_text and source_text and _sha(target_text) == _sha(source_text))
        host = _host(str(record.get("page_url") or record.get("url") or ""))
        text_state = "not_provided"
        if exact_text:
            text_state = "exact_match"
        elif similarity is not None and similarity >= exact_text_threshold:
            text_state = "near_exact_match"
        elif similarity is not None and similarity >= close_text_threshold:
            text_state = "partial_or_close_match"
        elif similarity is not None:
            text_state = "material_text_difference_candidate"

        is_official_role = role in {"preferred_parliamentary_discovery", "official_primary", "official_source", "primary_official"}
        corroborated = bool(is_official_role and (sum(identity_matches.values()) >= 2 or exact_text or (similarity is not None and similarity >= exact_text_threshold)))
        if corroborated:
            official_match = True
        row = {
            "source_record_id": str(record.get("source_record_id") or record.get("candidate_key") or f"source_record_{index + 1}"),
            "source_id": source_id, "source_role": role, "page_url": record.get("page_url") or record.get("url"),
            "host": host or None, "identity_matches": identity_matches,
            "identity_conflicts": identity_conflicts, "text_similarity": round(similarity, 4) if similarity is not None else None,
            "text_comparison": text_state, "source_text_sha256": _sha(source_text),
            "staged_text_sha256": _sha(target_text), "official_role_corroboration_candidate": corroborated,
            "source_record_status": record.get("discovery_status") or record.get("status") or "provided_record",
        }
        comparisons.append(row)
        if identity_conflicts:
            findings.append({"code": "source_metadata_conflict", "severity": "high",
                             "source_id": source_id, "fields": identity_conflicts,
                             "note": "تعارض فراداده نیازمند بررسی منبع و سند اصلی است."})
        if text_state == "material_text_difference_candidate":
            findings.append({"code": "source_text_difference", "severity": "high", "source_id": source_id,
                             "note": "اختلاف متن به‌تنهایی اثبات‌کننده اصلاح یا نسخ نیست."})
        if role in {"secondary_discovery", "secondary"} and (exact_text or (similarity is not None and similarity >= exact_text_threshold)):
            findings.append({"code": "secondary_source_match_only", "severity": "info", "source_id": source_id,
                             "note": "تطبیق با منبع ثانویه، تأیید رسمی محسوب نمی‌شود."})

    if official_match:
        status = "official_source_match_candidate"
    elif comparisons:
        status = "source_comparison_inconclusive"
    else:
        status = "no_source_records_provided"
    if not official_match and comparisons:
        findings.append({"code": "official_confirmation_missing", "severity": "high",
                         "note": "در سوابق ارائه‌شده تطبیق قابل اتکا با منبع رسمی شناسایی نشد."})
    return SourceMatchReport(
        checked_at=datetime.now(timezone.utc).isoformat(), validator_version="4.5.0",
        document_id=doc_id, status=status, source_comparisons=comparisons, findings=findings,
        official_confirmation=False,
    )


def write_source_match_report(report: SourceMatchReport, output_path: str | Path) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report.to_dict(), ensure_ascii=False, indent=2)
    fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(payload); stream.flush(); os.fsync(stream.fileno())
        os.replace(temp_name, target)
    except Exception:
        try: os.unlink(temp_name)
        except OSError: pass
        raise
    return target
