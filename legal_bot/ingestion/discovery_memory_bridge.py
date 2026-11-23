# -*- coding: utf-8 -*-
"""Phase 10.2.2: source-registry/catalog bridge and durable discovery checkpoints.

Discovery adapters are injected by the caller. This module performs no network
requests, never upgrades source authority, and never writes active legal banks.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .document_catalog import DocumentCatalog
from .pipeline_contracts import stable_document_key
from .source_registry import SourceRegistry

CATALOG_TO_PIPELINE = {
    "law": "law", "amendment": "law", "regulation": "regulation", "bylaw": "regulation",
    "ruling": "supreme_court_ruling", "consultation": "advisory_opinion",
    "circular": "regulation", "directive": "regulation",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp): os.unlink(temp)


class DiscoveryMemoryBridge:
    """Connect injected source discovery to the durable catalog and cycle inputs."""
    def __init__(self, *, registry: SourceRegistry, catalog: DocumentCatalog, checkpoint_path: str | Path):
        self.registry = registry
        self.catalog = catalog
        self.checkpoint_path = Path(checkpoint_path)

    def _load(self) -> dict[str, Any]:
        if not self.checkpoint_path.exists():
            return {"schema_version": "10.2.2", "sources": {}, "audit": []}
        data = json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
        if data.get("schema_version") != "10.2.2" or not isinstance(data.get("sources"), dict):
            raise ValueError("invalid_discovery_checkpoint")
        return data

    def source_policy(self, source_id: str) -> dict[str, Any]:
        source = self.registry.get(source_id)
        if source is None:
            raise ValueError("source_not_registered")
        return {
            "source_id": source.source_id,
            "authority_level": source.authority_level,
            "status": source.status,
            "access_mode": source.access_mode,
            "network_permitted": source.status == "verified" and source.access_mode == "polite_public_read",
            "allowed_hosts": list(source.allowed_hosts),
            "canonical_roots": list(source.canonical_roots),
            "document_types": list(source.document_types),
            "secondary_only": source.authority_level == "secondary",
        }

    def ingest_discovery_batch(self, source_id: str, records: Iterable[Mapping[str, Any]], *,
                               actor_id: str = "discovery-adapter", reason: str = "source discovery batch",
                               next_cursor: str | None = None) -> dict[str, Any]:
        """Persist metadata before advancing source cursor; retries remain safe."""
        policy = self.source_policy(source_id)
        materialized = [dict(r) for r in records]
        for row in materialized:
            if row.get("source_id") != source_id:
                raise ValueError("discovery_record_source_mismatch")
        result = self.catalog.ingest(materialized, actor_id=actor_id, reason=reason)
        state = self._load()
        previous = state["sources"].get(source_id, {})
        state["sources"][source_id] = {
            "cursor": next_cursor if next_cursor is not None else previous.get("cursor"),
            "last_batch_at": _now(),
            "last_catalog_version": result["catalog_version"],
            "last_batch_count": len(materialized),
            "authority_at_scan": policy["authority_level"],
        }
        state["audit"].append({"at": _now(), "source_id": source_id, "catalog_version": result["catalog_version"],
                               "batch_count": len(materialized), "cursor_advanced": next_cursor is not None})
        _atomic_write(self.checkpoint_path, state)
        return {**result, "source_id": source_id, "cursor": state["sources"][source_id]["cursor"],
                "network_permitted": policy["network_permitted"], "secondary_only": policy["secondary_only"]}

    def get_cursor(self, source_id: str) -> str | None:
        return self._load()["sources"].get(source_id, {}).get("cursor")

    def pipeline_candidates(self, *, source_id: str | None = None) -> list[dict[str, Any]]:
        """Return only verified official-primary catalog entries as pipeline inputs."""
        rows = self.catalog.list_documents(source_id=source_id)
        candidates: list[dict[str, Any]] = []
        for row in rows:
            rec = row["record"]
            source = self.registry.get(rec["source_id"])
            if source is None or source.authority_level != "official_primary" or source.status != "verified":
                continue
            if row["discovery_status"] != "discovered":
                continue
            kind = CATALOG_TO_PIPELINE.get(rec["document_type"])
            if not kind:
                continue
            identity = {
                "source_id": rec["source_id"], "document_kind": kind,
                "issuer": rec.get("issuer"), "official_number": rec.get("document_number"),
                "approval_date": rec.get("approval_date") or rec.get("promulgation_date"),
                "external_id": rec.get("external_id"),
            }
            try:
                doc_id = stable_document_key(identity)
            except ValueError:
                # Catalog identity may be stable source-scoped while pipeline
                # identity is not; do not invent a title-derived identifier.
                continue
            candidates.append({
                **identity, "document_id": doc_id, "title": rec["title"],
                "source_url": rec.get("document_url"), "content_sha256": rec.get("content_sha256"),
                "catalog_document_id": row["document_id"],
                "discovery_status": row["discovery_status"],
            })
        return candidates

    def status_report(self) -> dict[str, Any]:
        catalog_rows = self.catalog.list_documents()
        counts: dict[str, int] = {}
        for row in catalog_rows:
            status = row["discovery_status"]
            counts[status] = counts.get(status, 0) + 1
        return {"schema_version": "10.2.2", "catalog_total": len(catalog_rows),
                "discovery_status_counts": counts, "source_checkpoints": self._load()["sources"],
                "network_calls_performed": False, "active_bank_writes": False}
