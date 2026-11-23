# -*- coding: utf-8 -*-
"""Phase 7.1: deterministic architecture and bounded planning for bulk ingestion.

This module creates plans only. It never discovers sources, downloads assets,
parses documents, writes staging packages, or modifies the active legal bank.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "7.1"
DOC_PRIORITY = {
    "law": 10,
    "amendment": 20,
    "interpretation": 30,
    "ruling": 40,
    "consultation": 50,
    "circular": 60,
    "template": 70,
    "other": 90,
}
ALLOWED_SOURCE_CLASSES = {"official_primary", "secondary", "unverified"}


@dataclass(frozen=True)
class BatchPolicy:
    """Hard resource and trust limits for one proposed batch."""
    max_documents: int = 100
    max_total_bytes: int = 1_073_741_824
    max_ocr_pages: int = 5_000
    max_documents_per_source: int = 50
    allow_secondary_sources: bool = False
    allow_unverified_sources: bool = False
    default_estimated_bytes: int = 0
    default_estimated_pages: int = 0

    def validate(self) -> None:
        for field in ("max_documents", "max_total_bytes", "max_ocr_pages", "max_documents_per_source"):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{field} must be a positive integer")
        for field in ("default_estimated_bytes", "default_estimated_pages"):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field} must be a non-negative integer")


@dataclass(frozen=True)
class BulkWorkItem:
    document_id: str
    document_type: str
    source_id: str
    source_class: str
    estimated_bytes: int = 0
    estimated_pages: int = 0
    requires_ocr: bool = False
    explicit_priority: int | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any], policy: BatchPolicy) -> "BulkWorkItem":
        if not isinstance(raw, dict):
            raise ValueError("work item must be an object")
        document_id = str(raw.get("document_id", "")).strip()
        source_id = str(raw.get("source_id", "")).strip()
        document_type = str(raw.get("document_type", "other")).strip().lower()
        source_class = str(raw.get("source_class", "unverified")).strip().lower()
        if not document_id or not source_id:
            raise ValueError("document_id and source_id are required")
        if source_class not in ALLOWED_SOURCE_CLASSES:
            raise ValueError("unsupported source_class")
        if document_type not in DOC_PRIORITY:
            document_type = "other"
        size = raw.get("estimated_bytes", policy.default_estimated_bytes)
        pages = raw.get("estimated_pages", policy.default_estimated_pages)
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise ValueError("estimated_bytes must be a non-negative integer")
        if isinstance(pages, bool) or not isinstance(pages, int) or pages < 0:
            raise ValueError("estimated_pages must be a non-negative integer")
        priority = raw.get("explicit_priority")
        if priority is not None and (isinstance(priority, bool) or not isinstance(priority, int) or not 0 <= priority <= 1000):
            raise ValueError("explicit_priority must be an integer between 0 and 1000")
        return cls(document_id, document_type, source_id, source_class, size, pages,
                   bool(raw.get("requires_ocr", False)), priority)

    @property
    def priority(self) -> int:
        return self.explicit_priority if self.explicit_priority is not None else DOC_PRIORITY[self.document_type]

    @property
    def stable_key(self) -> str:
        raw = f"{self.source_id}\0{self.document_id}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()


def _source_permitted(item: BulkWorkItem, policy: BatchPolicy) -> bool:
    if item.source_class == "official_primary":
        return True
    if item.source_class == "secondary":
        return policy.allow_secondary_sources
    return policy.allow_unverified_sources


def create_batch_plan(candidates: Iterable[dict[str, Any]], *, policy: BatchPolicy | None = None) -> dict[str, Any]:
    """Create a deterministic bounded plan; no candidate is downloaded or imported."""
    policy = policy or BatchPolicy()
    policy.validate()
    accepted: list[BulkWorkItem] = []
    rejected: list[dict[str, str]] = []
    seen: dict[str, str] = {}
    duplicate_count = 0
    for index, raw in enumerate(candidates):
        try:
            item = BulkWorkItem.from_dict(raw, policy)
        except (TypeError, ValueError) as exc:
            rejected.append({"index": str(index), "reason": str(exc)})
            continue
        fingerprint = hashlib.sha256(json.dumps(asdict(item), sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        if item.stable_key in seen:
            if seen[item.stable_key] == fingerprint:
                duplicate_count += 1
            else:
                rejected.append({"index": str(index), "reason": "conflicting_duplicate_document_identity"})
            continue
        seen[item.stable_key] = fingerprint
        if not _source_permitted(item, policy):
            rejected.append({"index": str(index), "reason": f"source_class_not_permitted:{item.source_class}"})
            continue
        accepted.append(item)

    # Deterministic ordering: document type priority, then source and document IDs.
    accepted.sort(key=lambda x: (x.priority, x.source_id, x.document_id))
    selected: list[BulkWorkItem] = []
    deferred: list[dict[str, str]] = []
    source_counts: dict[str, int] = {}
    used_bytes = used_ocr_pages = 0
    for item in accepted:
        reason = None
        if len(selected) >= policy.max_documents:
            reason = "batch_document_limit"
        elif used_bytes + item.estimated_bytes > policy.max_total_bytes:
            reason = "batch_byte_budget"
        elif source_counts.get(item.source_id, 0) >= policy.max_documents_per_source:
            reason = "per_source_document_limit"
        elif item.requires_ocr and used_ocr_pages + item.estimated_pages > policy.max_ocr_pages:
            reason = "ocr_page_budget"
        if reason:
            deferred.append({"document_id": item.document_id, "source_id": item.source_id, "reason": reason})
            continue
        selected.append(item)
        used_bytes += item.estimated_bytes
        source_counts[item.source_id] = source_counts.get(item.source_id, 0) + 1
        if item.requires_ocr:
            used_ocr_pages += item.estimated_pages

    selected_payload = [asdict(item) | {"stable_key": item.stable_key, "priority": item.priority} for item in selected]
    plan_core = {
        "schema_version": SCHEMA_VERSION,
        "mode": "planning_only_dry_run",
        "policy": asdict(policy),
        "selected": selected_payload,
        "deferred": deferred,
        "rejected": rejected,
        "duplicates_skipped": duplicate_count,
        "resource_estimate": {
            "selected_documents": len(selected),
            "estimated_bytes": used_bytes,
            "estimated_ocr_pages": used_ocr_pages,
            "source_counts": dict(sorted(source_counts.items())),
        },
        "execution": {
            "network_access": False,
            "download_started": False,
            "pdf_processing_started": False,
            "staging_written": False,
            "active_bank_modified": False,
            "requires_phase7_2_source_registry": True,
        },
    }
    plan_id = hashlib.sha256(json.dumps(plan_core, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return {"plan_id": plan_id, **plan_core}


def write_batch_plan(plan: dict[str, Any], destination: str | Path) -> Path:
    """Atomically write a plan artifact to a caller-selected planning directory."""
    if not isinstance(plan, dict) or plan.get("schema_version") != SCHEMA_VERSION or plan.get("mode") != "planning_only_dry_run":
        raise ValueError("invalid phase 7.1 plan")
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(plan, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return path


def architecture_blueprint() -> dict[str, Any]:
    """Machine-readable target architecture; later phases implement each lane."""
    return {
        "schema_version": SCHEMA_VERSION,
        "components": [
            {"name": "source_registry", "phase": "7.2", "responsibility": "source authority, host allowlists, access policy"},
            {"name": "document_catalog", "phase": "7.3", "responsibility": "discovery inventory, identity and deduplication"},
            {"name": "bounded_acquisition_queue", "phase": "7.4", "responsibility": "rate-limited secure PDF acquisition"},
            {"name": "extraction_workers", "phase": "7.5", "responsibility": "text extraction, OCR and quality metrics"},
            {"name": "legal_structuring", "phase": "7.6", "responsibility": "legal hierarchy, normalization and lineage"},
            {"name": "validation_review_gate", "phase": "7.7", "responsibility": "technical/legal evidence and human review"},
            {"name": "search_shadow_evaluation", "phase": "7.8", "responsibility": "isolated search evaluation against golden queries"},
            {"name": "controlled_activation", "phase": "7.9", "responsibility": "approved transactional activation and monitoring"},
        ],
        "global_invariants": [
            "active_bank_is_read_only_until_explicit_phase_7_9_approval",
            "secondary_sources_never_substitute_for_official_primary_sources",
            "every_document_has_provenance_and_content_hashes",
            "untrusted_or_incomplete_documents_are_quarantined",
            "all_queues_are_bounded_deduplicated_and_restartable",
            "network_access_is_disabled_by_default",
            "human_legal_review_is_separate_from_technical_validation",
        ],
        "recommended_execution_model": {
            "control_plane": "persistent metadata and bounded queues",
            "data_plane": "immutable original PDFs and derived artifacts",
            "workers": ["discovery", "acquisition", "extraction", "ocr", "validation"],
            "isolation": "separate staging, quarantine, archive and active-bank namespaces",
            "backpressure": "document_count_byte_budget_ocr_page_budget_per_source_limit",
            "recovery": "checkpointed idempotent jobs with bounded retries and explicit resume",
        },
        "phase_7_1_scope": "architecture_and_deterministic_batch_planning_only",
    }
