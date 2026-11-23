# -*- coding: utf-8 -*-
"""Normalized records shared by all legal-source connectors."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

class DiscoveryStatus(str, Enum):
    DISCOVERED = "discovered"
    NO_ASSET = "no_asset"
    SOURCE_UNAVAILABLE = "source_unavailable"
    RETRY_LATER = "retry_later"
    ACCESS_CHALLENGE = "access_challenge"
    INVALID_RESPONSE = "invalid_response"

@dataclass(frozen=True)
class CandidateDocument:
    source_id: str
    source_name: str
    source_role: str
    document_type: str
    title: str
    page_url: str
    asset_url: str | None = None
    source_record_id: str | None = None
    issuer: str | None = None
    document_number: str | None = None
    document_date: str | None = None
    page_date: str | None = None
    discovered_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    http_status: int | None = None
    content_type: str | None = None
    content_length: int | None = None
    discovery_status: str = DiscoveryStatus.DISCOVERED.value
    notes: str = ""
    document_family: str | None = None
    catalog_document_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def stable_key(self) -> str:
        """Idempotency key; asset URL wins, otherwise source page + record ID/title."""
        import hashlib
        if self.catalog_document_id:
            raw = "catalog-document\n" + self.catalog_document_id
        else:
            raw = "\n".join((self.source_id, self.asset_url or self.page_url,
                             self.source_record_id or "", self.document_type,
                             self.title.strip()))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

@dataclass
class DiscoveryBatch:
    source_id: str
    category: str
    candidates: list[CandidateDocument] = field(default_factory=list)
    status: str = "ok"
    pages_seen: int = 0
    warnings: list[str] = field(default_factory=list)
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finished_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"source_id": self.source_id, "category": self.category,
                "status": self.status, "pages_seen": self.pages_seen,
                "candidate_count": len(self.candidates),
                "candidates": [c.to_dict() for c in self.candidates],
                "warnings": self.warnings, "started_at": self.started_at,
                "finished_at": self.finished_at}
