# -*- coding: utf-8 -*-
"""Policy-gated bridge from discovered catalog records into the PDF queue.

Only catalog records with a direct asset URL, an eligible discovery status and
an explicitly permitted source URL can enter the queue. This module plans work;
it never performs network I/O or writes active legal banks.
"""
from __future__ import annotations

from typing import Any

from .download_queue import DownloadQueue
from .models import CandidateDocument
from .source_registry import SourceRegistry

_ELIGIBLE_STATUSES = {"discovered"}


class CatalogDownloadBridge:
    def __init__(self, *, registry: SourceRegistry, queue: DownloadQueue):
        self.registry = registry
        self.queue = queue

    def enqueue_catalog(self, catalog: Any, *, source_id: str | None = None) -> dict[str, Any]:
        """Queue eligible catalog assets; quarantine/metadata-only rows are skipped."""
        rows = catalog.list_documents(source_id=source_id)
        candidates: list[CandidateDocument] = []
        skipped = {"not_eligible_status": 0, "no_direct_asset": 0,
                   "source_not_registered": 0, "source_policy_denied": 0,
                   "queue_host_not_allowlisted": 0}
        for row in rows:
            status = row.get("discovery_status")
            if status not in _ELIGIBLE_STATUSES:
                skipped["not_eligible_status"] += 1
                continue
            record = row.get("record") or {}
            asset_url = record.get("asset_url")
            if not asset_url:
                skipped["no_direct_asset"] += 1
                continue
            sid = str(record.get("source_id") or "")
            source = self.registry.get(sid)
            if source is None:
                skipped["source_not_registered"] += 1
                continue
            if not source.permits_url(asset_url):
                skipped["source_policy_denied"] += 1
                continue
            from urllib.parse import urlparse
            host = (urlparse(asset_url).hostname or "").lower().rstrip(".")
            if host not in self.queue.allowed_hosts:
                skipped["queue_host_not_allowlisted"] += 1
                continue
            candidate = CandidateDocument(
                source_id=sid,
                source_name=str(record.get("source_name") or source.display_name),
                source_role=str(record.get("source_role") or ""),
                document_type=str(record.get("connector_document_type") or record.get("document_type") or "other"),
                title=str(record.get("title") or ""),
                page_url=str(record.get("discovery_page_url") or record.get("document_url") or ""),
                asset_url=str(asset_url),
                source_record_id=record.get("source_record_id") or record.get("external_id"),
                issuer=record.get("issuer"),
                document_date=record.get("source_document_date"),
                notes=str(record.get("notes") or ""),
                document_family=record.get("document_family"),
                catalog_document_id=str(row.get("document_id") or ""),
            )
            candidates.append(candidate)
        queue_result = self.queue.enqueue(candidates)
        return {
            **queue_result,
            "catalog_rows_seen": len(rows),
            "eligible_candidates": len(candidates),
            "skipped": skipped,
            "network_calls_performed": False,
            "downloads_performed": False,
            "active_bank_writes": False,
        }
