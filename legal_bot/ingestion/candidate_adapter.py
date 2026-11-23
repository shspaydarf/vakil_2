# -*- coding: utf-8 -*-
"""Convert connector candidates into the durable catalog contract.

This adapter is metadata-only: it performs no network access, authority upgrade,
legal-effect inference, download, or active-bank write.
"""
from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any
from urllib.parse import urlparse

from .document_catalog import DOCUMENT_TYPES, DocumentRecord
from .models import CandidateDocument, DiscoveryBatch

# Explicit mappings only. Unknown connector types fail closed instead of guessing.
_TYPE_MAP: dict[str, tuple[str, str | None]] = {
    "parliamentary_law_record": ("law", "laws"),
    "parliamentary_law_pdf": ("law", "laws"),
    "law_candidate": ("law", "laws"),
    "law_record": ("law", "laws"),
    "regulation_candidate": ("regulation", "regulations_and_bylaws"),
    "regulation_record": ("regulation", "regulations_and_bylaws"),
    "national_regulation_record": ("regulation", "regulations_and_bylaws"),
    "national_regulation_pdf": ("regulation", "regulations_and_bylaws"),
    "supreme_court_ruling_candidate": ("ruling", "supreme_court_unity_rulings"),
    "supreme_court_ruling_record": ("ruling", "supreme_court_unity_rulings"),
    "supreme_court_ruling_collection": ("ruling", "supreme_court_unity_rulings"),
    "supreme_court_ruling_archive_bundle": ("ruling", "supreme_court_unity_rulings"),
    "administrative_court_ruling_candidate": ("ruling", "administrative_justice_general_assembly_rulings"),
    "administrative_court_ruling_record": ("ruling", "administrative_justice_general_assembly_rulings"),
    "advisory_opinion_candidate": ("consultation", "judiciary_advisory_opinions"),
    "advisory_opinion_collection_record": ("consultation", "judiciary_advisory_opinions"),
    "judiciary_document_record": ("other", None),
    "official_gazette_publication_record": ("other", None),
    "official_gazette_publication_pdf": ("other", None),
}
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def _date(value: str | None) -> str | None:
    if not value:
        return None
    normalized = str(value).strip().translate(_DIGITS)
    # Catalog accepts only Gregorian-style numeric precision; preserve unknown forms
    # in notes rather than silently reinterpret Jalali/Gregorian calendar semantics.
    if re.fullmatch(r"\d{4}(?:-\d{2}(?:-\d{2})?)?", normalized):
        return normalized
    return None


def _safe_https(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(str(value).strip())
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError("candidate_url_must_be_https_without_credentials")
    return str(value).strip()


def candidate_to_catalog_record(candidate: CandidateDocument) -> DocumentRecord:
    """Map one connector candidate to a validated catalog record."""
    if not isinstance(candidate, CandidateDocument):
        raise TypeError("candidate_must_be_CandidateDocument")
    mapping = _TYPE_MAP.get(candidate.document_type)
    if mapping is None:
        raise ValueError("unsupported_connector_document_type:" + str(candidate.document_type))
    catalog_type, family = mapping
    page_url = _safe_https(candidate.page_url)
    asset_url = _safe_https(candidate.asset_url)
    # Prefer the actual asset when present; otherwise retain the source record page.
    canonical_url = asset_url or page_url
    if not canonical_url:
        raise ValueError("candidate_requires_page_or_asset_url")
    external_id = (candidate.source_record_id or "").strip() or candidate.stable_key
    notes = candidate.notes.strip()
    if candidate.document_date and _date(candidate.document_date) is None:
        notes = (notes + " | " if notes else "") + "تاریخ خام منبع بدون تفسیر تقویمی حفظ نشد: " + str(candidate.document_date)
    return DocumentRecord(
        source_id=candidate.source_id,
        document_type=catalog_type,
        title=candidate.title.strip(),
        external_id=external_id,
        document_url=canonical_url,
        approval_date=None,
        source_document_date=(str(candidate.document_date).strip().translate(_DIGITS) if candidate.document_date else None),
        issuer=(candidate.issuer or "").strip(),
        jurisdiction="IR",
        language="fa",
        document_family=family,
        source_role=candidate.source_role,
        source_name=candidate.source_name,
        source_record_id=candidate.source_record_id,
        discovery_page_url=page_url,
        asset_url=asset_url,
        connector_document_type=candidate.document_type,
        metadata_evidence_ref=page_url or "",
        discovery_method="connector_fixture_or_saved_html",
        notes=notes,
    )


def batch_to_catalog_records(batch: DiscoveryBatch) -> list[DocumentRecord]:
    """Convert a complete discovery batch; reject source mismatches atomically."""
    if not isinstance(batch, DiscoveryBatch):
        raise TypeError("batch_must_be_DiscoveryBatch")
    records: list[DocumentRecord] = []
    for candidate in batch.candidates:
        if candidate.source_id != batch.source_id:
            raise ValueError("discovery_batch_source_mismatch")
        records.append(candidate_to_catalog_record(candidate))
    return records


def mapping_summary() -> dict[str, Any]:
    return {
        "mapped_connector_types": sorted(_TYPE_MAP),
        "catalog_document_types": sorted(DOCUMENT_TYPES),
        "unknown_types_fail_closed": True,
        "calendar_conversion_performed": False,
        "authority_inferred": False,
        "network_access": False,
        "active_bank_write": False,
    }
