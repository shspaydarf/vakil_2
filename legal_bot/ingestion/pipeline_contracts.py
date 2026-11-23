# -*- coding: utf-8 -*-
"""Phase 10.1.2: canonical hand-off contracts for autonomous legal ingestion.

This module defines and validates the shared envelope between discovery,
identity/catalog, acquisition, extraction, validation, and bank import. It does
not perform network access, OCR, legal-status inference, scheduling, or writes
into active JSON banks.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any, Mapping
from urllib.parse import urlparse

CONTRACT_VERSION = "10.1.2"
DOCUMENT_KINDS = {
    "law", "regulation", "supreme_court_ruling",
    "administrative_court_ruling", "advisory_opinion",
}
LIFECYCLE_STATES = {
    "discovered", "identity_checked", "queued", "acquired", "extracted",
    "validated", "quarantined", "ready_for_import", "imported",
    "duplicate", "deferred", "rejected", "failed",
}
ALLOWED_TRANSITIONS = {
    "discovered": {"identity_checked", "deferred", "rejected", "failed"},
    "identity_checked": {"queued", "duplicate", "deferred", "rejected", "failed"},
    "queued": {"acquired", "deferred", "rejected", "failed"},
    "acquired": {"extracted", "quarantined", "deferred", "failed"},
    "extracted": {"validated", "quarantined", "deferred", "failed"},
    "validated": {"ready_for_import", "quarantined", "rejected"},
    "ready_for_import": {"imported", "quarantined", "failed"},
    "quarantined": {"queued", "rejected", "deferred"},
    "deferred": {"queued", "rejected"},
    "duplicate": set(), "imported": set(), "rejected": set(), "failed": set(),
}
_HEX64 = re.compile(r"^[a-f0-9]{64}$")
_ID = re.compile(r"^[a-z0-9][a-z0-9_.:-]{1,159}$")
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalize_text(value: Any) -> str:
    value = unicodedata.normalize("NFKC", str(value or ""))
    value = value.translate(str.maketrans({"ي": "ی", "ك": "ک", "ۀ": "ه"})).translate(_DIGITS)
    return re.sub(r"\s+", " ", value).strip().casefold()


def stable_document_key(document: Mapping[str, Any]) -> str:
    """Stable identity across source mirrors when official identifiers exist.

    Prefer issuer + document kind + official number/date. Fall back to source
    scoped external ID. Title-only identities are deliberately not accepted.
    """
    kind = normalize_text(document.get("document_kind"))
    issuer = normalize_text(document.get("issuer"))
    number = normalize_text(document.get("official_number") or document.get("document_number"))
    date = normalize_text(document.get("approval_date") or document.get("document_date"))
    source = normalize_text(document.get("source_id"))
    external = normalize_text(document.get("external_id"))
    if kind not in DOCUMENT_KINDS:
        raise ValueError("unsupported_document_kind")
    if issuer and number:
        basis = ["IR", issuer, kind, number, date]
    elif source and external:
        basis = ["source_scoped", source, kind, external]
    else:
        raise ValueError("stable_official_or_source_identifier_required")
    return "machina_doc_" + hashlib.sha256("\x1f".join(basis).encode("utf-8")).hexdigest()[:32]


def version_key(document_id: str, content_sha256: str) -> str:
    if not _ID.fullmatch(str(document_id)):
        raise ValueError("invalid_document_id")
    digest = str(content_sha256 or "").lower()
    if not _HEX64.fullmatch(digest):
        raise ValueError("invalid_content_sha256")
    return "machina_ver_" + hashlib.sha256(f"{document_id}\x1f{digest}".encode()).hexdigest()[:32]


def validate_envelope(envelope: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the shared pipeline envelope; return normalized safe summary."""
    if not isinstance(envelope, Mapping):
        raise ValueError("envelope_must_be_object")
    required = ("contract_version", "document_id", "document_kind", "source_id", "title", "state")
    missing = [key for key in required if not str(envelope.get(key) or "").strip()]
    if missing:
        raise ValueError("missing_required_fields:" + ",".join(missing))
    if envelope["contract_version"] != CONTRACT_VERSION:
        raise ValueError("unsupported_contract_version")
    if envelope["document_kind"] not in DOCUMENT_KINDS:
        raise ValueError("unsupported_document_kind")
    if envelope["state"] not in LIFECYCLE_STATES:
        raise ValueError("invalid_lifecycle_state")
    if not _ID.fullmatch(str(envelope["document_id"])) or not _ID.fullmatch(str(envelope["source_id"])):
        raise ValueError("invalid_identifier_format")
    if not str(envelope["title"]).strip():
        raise ValueError("document_title_required")
    content_hash = envelope.get("content_sha256")
    if content_hash is not None and not _HEX64.fullmatch(str(content_hash).lower()):
        raise ValueError("invalid_content_sha256")
    page_count = envelope.get("page_count")
    if page_count is not None and (isinstance(page_count, bool) or not isinstance(page_count, int) or page_count < 1):
        raise ValueError("invalid_page_count")
    source_url = envelope.get("source_url")
    if source_url is not None:
        parsed = urlparse(str(source_url))
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("source_url_must_be_safe_https")
    evidence = envelope.get("evidence")
    if evidence is not None and not isinstance(evidence, Mapping):
        raise ValueError("evidence_must_be_object")
    return {
        "contract_version": CONTRACT_VERSION,
        "document_id": str(envelope["document_id"]),
        "document_kind": str(envelope["document_kind"]),
        "source_id": str(envelope["source_id"]),
        "state": str(envelope["state"]),
        "has_content_hash": bool(content_hash),
        "page_count": page_count,
    }


def can_transition(current: str, target: str) -> bool:
    if current not in LIFECYCLE_STATES or target not in LIFECYCLE_STATES:
        return False
    return target in ALLOWED_TRANSITIONS[current]


def transition(envelope: Mapping[str, Any], target: str) -> dict[str, Any]:
    validate_envelope(envelope)
    current = str(envelope["state"])
    if not can_transition(current, target):
        raise ValueError(f"illegal_state_transition:{current}->{target}")
    updated = dict(envelope)
    updated["state"] = target
    return updated


def make_envelope(*, source_id: str, document_kind: str, title: str,
                  document_id: str, source_url: str | None = None,
                  external_id: str | None = None) -> dict[str, Any]:
    result = {
        "contract_version": CONTRACT_VERSION,
        "document_id": document_id,
        "document_kind": document_kind,
        "source_id": source_id,
        "external_id": external_id,
        "title": title,
        "source_url": source_url,
        "state": "discovered",
        "content_sha256": None,
        "page_count": None,
        "evidence": {},
        "timestamps": {},
        "warnings": [],
    }
    validate_envelope(result)
    return result
