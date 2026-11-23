# -*- coding: utf-8 -*-
"""Phase 7.4: bounded, fail-closed batch acquisition of official PDFs.

Planning is offline and dry-run by default. Live acquisition requires an explicit
policy opt-in, a verified official-primary source, catalog eligibility, and the
existing SecurePDFDownloader. No OCR, legal validation, or active-bank writes occur.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "7.4"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class BatchAcquisitionPolicy:
    allow_downloads: bool = False
    max_documents: int = 10
    max_total_bytes: int = 100 * 1024 * 1024
    max_total_pages: int = 2000
    max_documents_per_source: int = 10

    def validate(self) -> None:
        for name in ("max_documents", "max_total_bytes", "max_total_pages", "max_documents_per_source"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if not isinstance(self.allow_downloads, bool):
            raise ValueError("allow_downloads must be boolean")


@dataclass(frozen=True)
class BatchCandidate:
    document_id: str
    source_id: str
    url: str
    title: str


class BatchPDFAcquisition:
    def __init__(self, *, policy: BatchAcquisitionPolicy | None = None, sleep_fn: Any = time.sleep):
        self.policy = policy or BatchAcquisitionPolicy()
        self.policy.validate()
        self.sleep_fn = sleep_fn

    def plan(self, catalog: Any, source_registry: Any, document_ids: Iterable[str]) -> dict[str, Any]:
        """Create a deterministic offline plan; never opens a network connection."""
        rows = catalog.load()["documents"]
        candidates: list[BatchCandidate] = []
        rejected: list[dict[str, str]] = []
        seen: set[str] = set()
        per_source: dict[str, int] = {}
        for doc_id in sorted(set(str(x) for x in document_ids)):
            row = rows.get(doc_id)
            if row is None:
                rejected.append({"document_id": doc_id, "reason": "document_not_in_catalog"})
                continue
            record = row["record"]
            source_id = record["source_id"]
            source = source_registry.get(source_id)
            if source is None:
                rejected.append({"document_id": doc_id, "reason": "source_not_registered"})
                continue
            if source.authority_level != "official_primary" or source.status != "verified":
                rejected.append({"document_id": doc_id, "reason": "source_not_verified_official_primary"})
                continue
            if row.get("discovery_status") != "discovered":
                rejected.append({"document_id": doc_id, "reason": "catalog_status_not_download_eligible"})
                continue
            url = record.get("document_url")
            if not url or not source.permits_url(url):
                rejected.append({"document_id": doc_id, "reason": "url_not_permitted_by_source_registry"})
                continue
            if doc_id in seen:
                continue
            if len(candidates) >= self.policy.max_documents:
                rejected.append({"document_id": doc_id, "reason": "batch_document_budget_exceeded"})
                continue
            source_limit = min(self.policy.max_documents_per_source, source.max_pages_per_run)
            if per_source.get(source_id, 0) >= source_limit:
                rejected.append({"document_id": doc_id, "reason": "per_source_budget_exceeded"})
                continue
            candidates.append(BatchCandidate(doc_id, source_id, url, record["title"]))
            seen.add(doc_id)
            per_source[source_id] = per_source.get(source_id, 0) + 1
        payload = {
            "schema_version": SCHEMA_VERSION,
            "plan_id": _hash({"candidates": [asdict(x) for x in candidates], "policy": asdict(self.policy)}),
            "created_at": _now(), "dry_run": True,
            "policy": asdict(self.policy),
            "candidates": [asdict(x) for x in candidates],
            "rejected": rejected,
            "network_access_performed": False,
            "active_bank_write": False,
        }
        return payload

    def execute(self, plan: dict[str, Any], *, catalog: Any, source_registry: Any,
                downloader: Any, state_path: str | Path, actor_id: str,
                dry_run: bool = True) -> dict[str, Any]:
        """Execute sequentially. No retries; 403/429/challenges stop the batch."""
        if not actor_id.strip():
            raise ValueError("actor_id is required")
        if plan.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("invalid batch plan schema")
        if plan.get("plan_id") != _hash({"candidates": plan.get("candidates", []), "policy": plan.get("policy", {})}):
            raise ValueError("batch plan integrity check failed")
        if dry_run:
            return {"schema_version": SCHEMA_VERSION, "plan_id": plan["plan_id"], "dry_run": True,
                    "status": "planned", "attempted": 0, "acquired": [], "deferred": [],
                    "network_access_performed": False, "active_bank_write": False}
        if not self.policy.allow_downloads:
            raise PermissionError("batch downloads are disabled by policy")
        if not getattr(getattr(downloader, "policy", None), "allow_downloads", False):
            raise PermissionError("SecurePDFDownloader downloads are disabled")
        state_file = Path(state_path)
        prior = _load_state(state_file)
        acquired: list[dict[str, Any]] = []
        deferred: list[dict[str, str]] = []
        total_bytes = sum(int(x.get("size_bytes", 0)) for x in prior.get("acquired", []))
        total_pages = sum(int(x.get("page_count", 0)) for x in prior.get("acquired", []))
        total_docs = len(prior.get("acquired", []))
        per_source: dict[str, int] = {}
        last_request_at: dict[str, float] = {}
        for item in prior.get("acquired", []):
            per_source[item.get("source_id", "")] = per_source.get(item.get("source_id", ""), 0) + 1
        stop_reason: str | None = None
        for candidate in plan.get("candidates", []):
            doc_id = candidate["document_id"]
            if any(x.get("document_id") == doc_id for x in prior.get("acquired", [])):
                continue
            if stop_reason:
                deferred.append({"document_id": doc_id, "reason": stop_reason}); continue
            current_source = source_registry.get(candidate["source_id"])
            source_limit = min(self.policy.max_documents_per_source, current_source.max_pages_per_run) if current_source else 0
            if total_docs >= self.policy.max_documents or per_source.get(candidate["source_id"], 0) >= source_limit:
                deferred.append({"document_id": doc_id, "reason": "document_budget_exceeded"}); continue
            remaining_bytes = self.policy.max_total_bytes - total_bytes
            remaining_pages = self.policy.max_total_pages - total_pages
            fetch_cap = getattr(getattr(downloader, "policy", None), "max_asset_bytes", None)
            if remaining_bytes <= 0 or remaining_pages <= 0 or not isinstance(fetch_cap, int) or fetch_cap > remaining_bytes:
                deferred.append({"document_id": doc_id, "reason": "remaining_batch_budget_below_safe_fetch_cap"}); continue
            row = catalog.load()["documents"].get(doc_id)
            source = source_registry.get(candidate["source_id"])
            if row is None or row.get("discovery_status") != "discovered" or source is None:
                deferred.append({"document_id": doc_id, "reason": "catalog_or_source_state_changed"}); continue
            if source.authority_level != "official_primary" or source.status != "verified" or not source.permits_url(candidate["url"]):
                deferred.append({"document_id": doc_id, "reason": "source_policy_revalidation_failed"}); continue
            if candidate["url"] != row["record"].get("document_url"):
                deferred.append({"document_id": doc_id, "reason": "plan_url_catalog_mismatch"}); continue
            try:
                previous_request = last_request_at.get(candidate["source_id"])
                if previous_request is not None:
                    wait_seconds = current_source.min_request_interval_seconds - (time.monotonic() - previous_request)
                    if wait_seconds > 0:
                        self.sleep_fn(wait_seconds)
                last_request_at[candidate["source_id"]] = time.monotonic()
                result = downloader.download(candidate["url"])
                if result.size_bytes > remaining_bytes or result.page_count > remaining_pages:
                    # The downloader has already enforced its per-file hard cap. Keep the original
                    # quarantined, but do not count it as an accepted batch acquisition.
                    deferred.append({"document_id": doc_id, "reason": "actual_batch_budget_exceeded_file_retained_for_review"})
                    stop_reason = "batch_resource_budget_reached"
                    continue
                entry = {"document_id": doc_id, "source_id": candidate["source_id"], **result.to_dict()}
                acquired.append(entry); prior.setdefault("acquired", []).append(entry)
                total_bytes += result.size_bytes; total_pages += result.page_count; total_docs += 1
                per_source[candidate["source_id"]] = per_source.get(candidate["source_id"], 0) + 1
                _write_state(state_file, prior)
            except Exception as exc:
                message = str(exc)
                category = "download_failed"
                if "403" in message or "CAPTCHA" in message.upper() or "challenge" in message.lower():
                    category = "access_blocked_no_bypass"; stop_reason = category
                elif "429" in message:
                    category = "rate_limited_deferred"; stop_reason = category
                deferred.append({"document_id": doc_id, "reason": category, "detail": message[:300]})
                if stop_reason:
                    continue
        result_state = {"schema_version": SCHEMA_VERSION, "batch_id": plan["plan_id"],
                        "updated_at": _now(), "actor_id": actor_id,
                        "acquired": prior.get("acquired", []), "last_run_acquired": acquired,
                        "last_run_deferred": deferred, "total_bytes": total_bytes,
                        "total_pages": total_pages, "network_access_performed": bool(acquired or deferred),
                        "active_bank_write": False}
        _write_state(state_file, result_state)
        return {"schema_version": SCHEMA_VERSION, "plan_id": plan["plan_id"], "dry_run": False,
                "status": "completed_with_deferrals" if deferred else "completed",
                "attempted": len(acquired) + len(deferred), "acquired": acquired, "deferred": deferred,
                "total_bytes": total_bytes, "total_pages": total_pages,
                "network_access_performed": bool(acquired or deferred), "active_bank_write": False}


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "acquired": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA_VERSION or not isinstance(data.get("acquired"), list):
        raise ValueError("invalid acquisition state")
    return data


def _write_state(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.flush(); os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def acquisition_policy_summary() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "downloads_default_off": True,
            "verified_official_primary_only": True, "sequential_no_automatic_retry": True,
            "stop_on_403_429_or_challenge": True, "preserve_original_pdf": True,
            "sha256_content_addressing": True, "active_bank_write": False,
            "secondary_source_substitution": False}
