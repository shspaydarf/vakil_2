# -*- coding: utf-8 -*-
"""Phase 10.2.1: fail-closed orchestration spine for legal document ingestion.

This module wires injected adapters in a deterministic order. It performs no
network access itself and never writes active JSON banks unless an explicit
import adapter is supplied by the caller.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .pipeline_contracts import (
    CONTRACT_VERSION, make_envelope, stable_document_key, transition,
    validate_envelope, version_key,
)

Adapter = Callable[[dict[str, Any]], Mapping[str, Any]]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(dict(value), stream, ensure_ascii=False, indent=2)
            stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": "10.2.1", "documents": {}, "runs": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != "10.2.1" or not isinstance(data.get("documents"), dict):
        raise ValueError("invalid_or_unsupported_orchestration_state")
    return data


def _merge(base: dict[str, Any], result: Mapping[str, Any] | None) -> dict[str, Any]:
    if result is None:
        return base
    if not isinstance(result, Mapping):
        raise ValueError("adapter_result_must_be_mapping")
    merged = dict(base); merged.update(dict(result)); return merged


def run_ingestion_cycle(
    candidates: Iterable[Mapping[str, Any]], *, state_path: str | Path,
    acquire: Adapter, extract: Adapter, validate: Adapter,
    import_document: Adapter | None = None, max_candidates: int = 100,
    max_pages: int = 20,
) -> dict[str, Any]:
    """Run discovered candidates through identity, acquisition, extraction,
    validation and optional import. Adapters are injected and independently
    testable. State is persisted after each candidate for crash-safe resumption.
    """
    if not 1 <= max_candidates <= 100 or not 1 <= max_pages <= 20:
        raise ValueError("cycle_limits_out_of_range")
    state_file = Path(state_path)
    state = _load_state(state_file)
    run = {"run_id": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"),
           "started_at": _now(), "discovered": 0, "processed": 0,
           "duplicates": 0, "deferred": 0, "quarantined": 0,
           "failed": 0, "imported": 0, "pages_used": 0,
           "import_enabled": import_document is not None, "items": []}

    for index, raw in enumerate(candidates):
        if index >= max_candidates:
            run["deferred"] += 1
            run["items"].append({"index": index, "state": "deferred", "reason": "candidate_limit_reached"})
            continue
        run["discovered"] += 1
        try:
            candidate = dict(raw)
            doc_id = candidate.get("document_id") or stable_document_key(candidate)
            envelope = make_envelope(
                source_id=str(candidate["source_id"]),
                document_kind=str(candidate["document_kind"]),
                title=str(candidate["title"]), document_id=str(doc_id),
                source_url=candidate.get("source_url"),
                external_id=candidate.get("external_id"),
            )
            validate_envelope(envelope)
            digest_seen = state["documents"].get(doc_id, {}).get("content_sha256")
            if digest_seen and candidate.get("content_sha256") == digest_seen:
                run["duplicates"] += 1
                run["items"].append({"document_id": doc_id, "state": "duplicate", "reason": "same_document_version_already_processed"})
                continue
            envelope = transition(envelope, "identity_checked")
            candidate["document_id"] = doc_id
            acquired = _merge(candidate, acquire(candidate))
            pages = acquired.get("page_count")
            if isinstance(pages, bool) or not isinstance(pages, int) or pages < 1:
                raise ValueError("acquisition_page_count_invalid")
            if pages > max_pages or run["pages_used"] + pages > max_pages:
                run["deferred"] += 1
                run["items"].append({"document_id": doc_id, "state": "deferred", "reason": "run_page_budget_exceeded", "page_count": pages})
                continue
            run["pages_used"] += pages
            envelope = transition(envelope, "queued")
            envelope = transition(envelope, "acquired")
            extracted = _merge(acquired, extract(acquired))
            digest = str(extracted.get("content_sha256") or "").lower()
            if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
                raise ValueError("extraction_content_sha256_invalid")
            extracted["content_sha256"] = digest
            extracted["page_count"] = pages
            envelope.update({"content_sha256": digest, "page_count": pages})
            envelope = transition(envelope, "extracted")
            verdict = dict(validate(extracted))
            if verdict.get("accepted") is not True or verdict.get("primary_source_verified") is not True:
                envelope = transition(envelope, "quarantined")
                run["quarantined"] += 1
                run["items"].append({"document_id": doc_id, "state": "quarantined", "reason": verdict.get("reason", "validation_or_primary_source_not_confirmed")})
                state["documents"][doc_id] = {"content_sha256": digest, "state": "quarantined", "updated_at": _now()}
                _atomic_json(state_file, state)
                continue
            envelope = transition(envelope, "validated")
            envelope = transition(envelope, "ready_for_import")
            imported = False
            if import_document is not None:
                import_result = dict(import_document(extracted))
                imported = import_result.get("imported") is True
                if not imported:
                    raise ValueError("import_adapter_did_not_confirm_import")
                envelope = transition(envelope, "imported")
                run["imported"] += 1
            state["documents"][doc_id] = {
                "content_sha256": digest,
                "version_key": version_key(doc_id, digest),
                "state": "imported" if imported else "ready_for_import",
                "updated_at": _now(),
            }
            run["processed"] += 1
            run["items"].append({"document_id": doc_id, "state": envelope["state"], "version_key": version_key(doc_id, digest)})
        except Exception as exc:
            run["failed"] += 1
            run["items"].append({"index": index, "state": "failed", "reason": str(exc)[:240]})
        _atomic_json(state_file, state)

    run["completed_at"] = _now()
    state["runs"].append({k: run[k] for k in ("run_id", "started_at", "completed_at", "discovered", "processed", "duplicates", "deferred", "quarantined", "failed", "imported", "pages_used")})
    _atomic_json(state_file, state)
    return run
