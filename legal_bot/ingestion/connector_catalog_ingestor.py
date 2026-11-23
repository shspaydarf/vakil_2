# -*- coding: utf-8 -*-
"""Offline connector-to-registry-to-catalog ingestion adapter.

Consumes caller-supplied/saved HTML only. It never performs network I/O, downloads
assets, upgrades source authority, or writes active legal banks.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any
from urllib.parse import urlparse

from .candidate_adapter import batch_to_catalog_records
from .discovery_memory_bridge import DiscoveryMemoryBridge
from .document_catalog import DocumentCatalog
from .models import DiscoveryBatch
from .source_registry import SourceRegistry


class ConnectorCatalogIngestor:
    """Run one fixture/saved-HTML discovery through registry policy and catalog."""

    def __init__(self, *, registry: SourceRegistry, catalog: DocumentCatalog,
                 checkpoint_path: str):
        self.registry = registry
        self.catalog = catalog
        self.bridge = DiscoveryMemoryBridge(
            registry=registry, catalog=catalog, checkpoint_path=checkpoint_path
        )

    @staticmethod
    def _host(url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("connector_url_must_be_https_without_credentials")
        if parsed.port not in (None, 443):
            raise ValueError("connector_url_must_use_default_https_port")
        return parsed.hostname.lower().rstrip(".")

    def ingest_saved_html(self, connector: Any, html: str, page_url: str, *,
                          category: str, actor_id: str = "connector-ingestor",
                          reason: str = "saved HTML connector discovery",
                          next_cursor: str | None = None) -> dict[str, Any]:
        """Parse supplied HTML, enforce source policy, adapt and persist catalog metadata."""
        definition = getattr(connector, "definition", None)
        if definition is None:
            raise TypeError("connector_definition_required")
        source_id = str(getattr(definition, "source_id", "")).strip()
        if not source_id:
            raise ValueError("connector_source_id_required")
        source = self.registry.get(source_id)
        if source is None:
            raise ValueError("source_not_registered")

        connector_hosts = {str(x).lower().rstrip(".") for x in getattr(definition, "allowed_hosts", ())}
        if not connector_hosts or not (connector_hosts & set(source.allowed_hosts)):
            raise ValueError("connector_and_registry_hosts_do_not_overlap")
        page_host = self._host(page_url)
        if page_host not in connector_hosts or not source.recognizes_url(page_url):
            raise ValueError("discovery_page_not_allowed_by_connector_and_registry")

        # This is a parser call over already supplied HTML, not a network operation.
        candidates = list(connector.discover_from_html(html or "", page_url, category=category))
        batch = connector.make_batch(category, candidates, pages_seen=1)
        if not isinstance(batch, DiscoveryBatch) or batch.source_id != source_id:
            raise ValueError("connector_batch_source_mismatch")
        records = batch_to_catalog_records(batch)
        for record in records:
            for candidate_url in (record.discovery_page_url, record.asset_url, record.document_url):
                if candidate_url:
                    host = self._host(candidate_url)
                    if host not in connector_hosts or not source.recognizes_url(candidate_url):
                        raise ValueError("candidate_url_not_allowed_by_connector_and_registry")
            if source.document_types and record.document_type not in source.document_types:
                raise ValueError("document_type_not_allowed_by_source_registry")

        result = self.bridge.ingest_discovery_batch(
            source_id, [asdict(record) for record in records], actor_id=actor_id,
            reason=reason, next_cursor=next_cursor,
        )
        return {
            **result,
            "candidate_count": len(batch.candidates),
            "source_status": source.status,
            "source_authority": source.authority_level,
            "network_calls_performed": False,
            "downloads_performed": False,
            "active_bank_writes": False,
        }
