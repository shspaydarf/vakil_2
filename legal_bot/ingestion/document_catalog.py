# -*- coding: utf-8 -*-
"""Phase 7.3: auditable document discovery catalog (metadata only).

No network discovery, downloads, PDF/OCR processing, legal-validity decisions,
source-authority upgrades, or active-bank writes occur in this module.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse, urlunparse

SCHEMA_VERSION = "7.3"
DOCUMENT_TYPES = {"law", "amendment", "regulation", "bylaw", "ruling", "consultation", "circular", "directive", "template", "other"}
DISCOVERY_STATUSES = {"discovered", "metadata_incomplete", "quarantined", "duplicate_content", "retired"}
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.:-]{1,159}$")
_SHA_RE = re.compile(r"^[a-f0-9]{64}$")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _preserve_safe_url(value: str | None) -> str | None:
    """Validate provenance/download URL while preserving query parameters."""
    if not value:
        return None
    parsed = urlparse(str(value).strip())
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("source URL must be HTTPS and contain no credentials")
    if parsed.port not in (None, 443):
        raise ValueError("source URL port must be default HTTPS")
    return str(value).strip()


def _canonical_url(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(str(value).strip())
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("document_url must be HTTPS and contain no credentials")
    if parsed.port not in (None, 443):
        raise ValueError("document_url port must be default HTTPS")
    # Query strings/fragments are excluded from identity; paths remain case-sensitive.
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    return urlunparse(("https", parsed.hostname.lower().rstrip("."), path.rstrip("/") or "/", "", "", ""))


@dataclass(frozen=True)
class DocumentRecord:
    source_id: str
    document_type: str
    title: str
    external_id: str = ""
    document_url: str | None = None
    publication_date: str | None = None
    approval_date: str | None = None
    promulgation_date: str | None = None
    document_number: str | None = None
    issuer: str = ""
    jurisdiction: str = "IR"
    language: str = "fa"
    content_sha256: str | None = None
    page_count: int | None = None
    related_document_ids: tuple[str, ...] = ()
    relationship_hints: tuple[str, ...] = ()
    metadata_evidence_ref: str = ""
    discovery_method: str = "manual_or_imported_metadata"
    notes: str = ""
    # Connector provenance fields; optional for backward compatibility with schema 7.3.
    document_family: str | None = None
    source_role: str = ""
    source_name: str = ""
    source_record_id: str | None = None
    discovery_page_url: str | None = None
    asset_url: str | None = None
    connector_document_type: str = ""
    source_document_date: str | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "DocumentRecord":
        if not isinstance(raw, dict):
            raise ValueError("document record must be an object")
        record = cls(
            source_id=str(raw.get("source_id", "")).strip().lower(),
            document_type=str(raw.get("document_type", "other")).strip().lower(),
            title=str(raw.get("title", "")).strip(),
            external_id=str(raw.get("external_id", "")).strip(),
            document_url=_canonical_url(raw.get("document_url")),
            publication_date=raw.get("publication_date"), approval_date=raw.get("approval_date"),
            promulgation_date=raw.get("promulgation_date"), document_number=raw.get("document_number"),
            issuer=str(raw.get("issuer", "")).strip(), jurisdiction=str(raw.get("jurisdiction", "IR")).strip(),
            language=str(raw.get("language", "fa")).strip(),
            content_sha256=str(raw["content_sha256"]).lower() if raw.get("content_sha256") else None,
            page_count=raw.get("page_count"),
            related_document_ids=tuple(sorted(set(str(x).strip() for x in raw.get("related_document_ids", ()) if str(x).strip()))),
            relationship_hints=tuple(sorted(set(str(x).strip() for x in raw.get("relationship_hints", ()) if str(x).strip()))),
            metadata_evidence_ref=str(raw.get("metadata_evidence_ref", "")).strip(),
            discovery_method=str(raw.get("discovery_method", "manual_or_imported_metadata")).strip(),
            notes=str(raw.get("notes", "")),
            document_family=raw.get("document_family"),
            source_role=str(raw.get("source_role", "")),
            source_name=str(raw.get("source_name", "")),
            source_record_id=raw.get("source_record_id"),
            discovery_page_url=_preserve_safe_url(raw.get("discovery_page_url")),
            asset_url=_preserve_safe_url(raw.get("asset_url")),
            connector_document_type=str(raw.get("connector_document_type", "")),
            source_document_date=raw.get("source_document_date"),
        )
        record.validate()
        return record

    def validate(self) -> None:
        if not _ID_RE.fullmatch(self.source_id):
            raise ValueError("source_id must be a stable identifier")
        if self.document_type not in DOCUMENT_TYPES:
            raise ValueError("unsupported document_type")
        if not self.title:
            raise ValueError("title is required")
        if self.content_sha256 and not _SHA_RE.fullmatch(self.content_sha256):
            raise ValueError("content_sha256 must be a SHA-256 hex digest")
        if self.page_count is not None and (isinstance(self.page_count, bool) or not isinstance(self.page_count, int) or self.page_count < 1):
            raise ValueError("page_count must be a positive integer")
        for value in (self.publication_date, self.approval_date, self.promulgation_date):
            if value and not re.fullmatch(r"\d{4}(-\d{2}(-\d{2})?)?", str(value)):
                raise ValueError("dates must use YYYY, YYYY-MM or YYYY-MM-DD")
        if self.document_url and not self.document_url.startswith("https://"):
            raise ValueError("invalid canonical document URL")
        allowed_families = {"laws", "regulations_and_bylaws", "supreme_court_unity_rulings",
                            "administrative_justice_general_assembly_rulings", "judiciary_advisory_opinions"}
        if self.document_family is not None and self.document_family not in allowed_families:
            raise ValueError("unsupported document_family")

    @property
    def document_id(self) -> str:
        identity = self.external_id or self.document_url
        if not identity:
            # Metadata-only records must carry an external ID to be stable across imports.
            raise ValueError("external_id or document_url is required for stable document identity")
        return hashlib.sha256(f"{self.source_id}\0{identity}".encode("utf-8")).hexdigest()


class DocumentCatalog:
    """Versioned catalog with explicit source checks, deduplication and audit history."""
    def __init__(self, path: str | Path, source_registry: Any | None = None):
        self.path = Path(path)
        self.source_registry = source_registry

    def _empty(self) -> dict[str, Any]:
        return {"schema_version": SCHEMA_VERSION, "catalog_version": 0, "documents": {}, "audit": [], "duplicate_groups": {}}

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._empty()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if data.get("schema_version") != SCHEMA_VERSION or not isinstance(data.get("documents"), dict) or not isinstance(data.get("audit"), list):
            raise ValueError("invalid document catalog")
        for key, row in data["documents"].items():
            record = DocumentRecord.from_dict(row["record"])
            if key != record.document_id:
                raise ValueError("document catalog identity mismatch")
        return data

    def ingest(self, records: Iterable[DocumentRecord | dict[str, Any]], *, actor_id: str, reason: str,
               expected_version: int | None = None) -> dict[str, Any]:
        if not actor_id.strip() or not reason.strip():
            raise ValueError("actor_id and reason are required")
        data = self.load()
        if expected_version is not None and expected_version != data["catalog_version"]:
            raise RuntimeError("catalog_version_conflict")
        added = duplicates = quarantined = rejected = 0
        for index, raw in enumerate(records):
            try:
                item = raw if isinstance(raw, DocumentRecord) else DocumentRecord.from_dict(raw)
                item.validate()
                doc_id = item.document_id
                source = self.source_registry.get(item.source_id) if self.source_registry else None
                if self.source_registry and source is None:
                    raise ValueError("source_not_registered")
                # Validate every URL-bearing provenance field, not only the
                # canonical document URL. Cataloging metadata is not network
                # permission: acquisition must separately call permits_url().
                if self.source_registry is not None:
                    if source is None:
                        raise ValueError("source_not_registered")
                    recognizes = getattr(source, "recognizes_url", None)
                    if not callable(recognizes):
                        raise ValueError("source_registry_url_recognition_unavailable")
                    for field_name in ("document_url", "discovery_page_url", "asset_url"):
                        candidate_url = getattr(item, field_name)
                        if candidate_url and not recognizes(candidate_url):
                            raise ValueError(field_name + "_not_recognized_by_source_registry")
                if doc_id in data["documents"]:
                    old = data["documents"][doc_id]
                    if _hash(old["record"]) == _hash(asdict(item)):
                        duplicates += 1
                    else:
                        rejected += 1
                        data["audit"].append({"at": _now(), "actor_id": actor_id, "action": "identity_conflict_rejected", "document_id": doc_id, "reason": reason, "incoming_sha256": _hash(asdict(item))})
                    continue
                authority = source.authority_level if source else "unverified"
                status = "discovered" if authority == "official_primary" else "quarantined"
                if not item.title or not item.external_id and not item.document_url:
                    status = "metadata_incomplete"
                if status == "quarantined":
                    quarantined += 1
                row = {"record": asdict(item), "document_id": doc_id, "source_authority_at_discovery": authority,
                       "discovery_status": status, "discovered_at": _now(), "duplicate_of": None}
                data["documents"][doc_id] = row
                added += 1
            except (TypeError, ValueError) as exc:
                rejected += 1
                data["audit"].append({"at": _now(), "actor_id": actor_id, "action": "record_rejected", "index": index, "reason": str(exc)})
        # Exact content hashes identify duplicate content, but never merge legal identities.
        by_hash: dict[str, list[str]] = {}
        for doc_id, row in data["documents"].items():
            digest = row["record"].get("content_sha256")
            if digest:
                by_hash.setdefault(digest, []).append(doc_id)
        groups = {digest: sorted(ids) for digest, ids in by_hash.items() if len(ids) > 1}
        data["duplicate_groups"] = groups
        for ids in groups.values():
            for doc_id in ids:
                if data["documents"][doc_id]["discovery_status"] == "discovered":
                    data["documents"][doc_id]["discovery_status"] = "duplicate_content"
                data["documents"][doc_id]["duplicate_of"] = ids[0] if doc_id != ids[0] else None
        data["catalog_version"] += 1
        data["audit"].append({"version": data["catalog_version"], "at": _now(), "actor_id": actor_id,
                              "action": "catalog_ingest", "reason": reason, "added": added,
                              "duplicates_skipped": duplicates, "quarantined": quarantined, "rejected": rejected,
                              "catalog_sha256": _hash(data["documents"])})
        self._atomic_write(data)
        return {"catalog_version": data["catalog_version"], "added": added, "duplicates_skipped": duplicates,
                "quarantined": quarantined, "rejected": rejected, "total_documents": len(data["documents"]),
                "duplicate_groups": len(groups)}

    def list_documents(self, *, source_id: str | None = None, document_type: str | None = None,
                       status: str | None = None) -> list[dict[str, Any]]:
        rows = self.load()["documents"].values()
        result = []
        for row in rows:
            rec = row["record"]
            if source_id and rec["source_id"] != source_id: continue
            if document_type and rec["document_type"] != document_type: continue
            if status and row["discovery_status"] != status: continue
            result.append(row)
        return sorted(result, key=lambda x: (x["record"]["source_id"], x["record"]["document_type"], x["record"]["title"]))

    def _atomic_write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=self.path.name + ".", suffix=".tmp", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2, sort_keys=True)
                stream.flush(); os.fsync(stream.fileno())
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp): os.unlink(tmp)


def catalog_policy_summary() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "network_discovery": False, "downloads": False,
            "unknown_sources_quarantined": True, "secondary_sources_substitute_for_official": False,
            "content_hash_dedup_only": True, "legal_relationships_are_not_inferred_as_facts": True,
            "active_bank_write": False, "human_legal_review_required": True}
