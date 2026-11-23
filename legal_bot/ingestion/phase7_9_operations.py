# -*- coding: utf-8 -*-
"""Phase 7.9: bounded operations, monitoring, recovery and activation readiness.

This module prepares and monitors an operational rollout. It deliberately does
not fetch, process, import, commit, or activate documents. Production activation
remains a separate, explicitly authorized human operation outside this module.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .bulk_processing_architecture import BatchPolicy, create_batch_plan

SCHEMA_VERSION = "7.9"
TERMINAL_STATES = {"completed", "rejected", "blocked", "cancelled"}
ALLOWED_STATES = {"queued", "acquiring", "processing", "awaiting_review", "staged", *TERMINAL_STATES}


class Phase79Error(ValueError):
    """Invalid operational plan, checkpoint, or readiness evidence."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _canonical_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def create_rollout_plan(
    candidates: Iterable[dict[str, Any]], *, policy: BatchPolicy | None = None,
    rollout_id: str = "pilot-001", window_label: str = "manual-pilot",
) -> dict[str, Any]:
    """Create a deterministic, bounded rollout plan; planning only, no execution."""
    rollout_id = str(rollout_id).strip()
    window_label = str(window_label).strip()
    if not rollout_id or not window_label:
        raise Phase79Error("rollout_id_and_window_label_required")
    batch = create_batch_plan(candidates, policy=policy or BatchPolicy())
    selected = batch["selected"]
    items = [{
        "document_id": item["document_id"], "source_id": item["source_id"],
        "stable_key": item["stable_key"], "priority": item["priority"],
        "state": "queued", "attempts": 0, "last_error_code": None,
    } for item in selected]
    core = {
        "schema_version": SCHEMA_VERSION, "rollout_id": rollout_id,
        "window_label": window_label, "mode": "controlled_pilot_plan_only",
        "batch_plan_id": batch["plan_id"], "policy": batch["policy"],
        "items": items, "deferred": batch["deferred"], "rejected": batch["rejected"],
        "resource_estimate": batch["resource_estimate"],
        "safety": {"network_access": False, "download_started": False,
                   "processing_started": False, "staging_written": False,
                   "active_bank_write": False, "production_activation": False},
    }
    return {**core, "plan_sha256": _canonical_hash(core), "created_at": _utc_now()}


def validate_rollout_plan(plan: Mapping[str, Any]) -> None:
    if plan.get("schema_version") != SCHEMA_VERSION or plan.get("mode") != "controlled_pilot_plan_only":
        raise Phase79Error("invalid_phase7_9_rollout_plan")
    core = {k: v for k, v in plan.items() if k not in {"plan_sha256", "created_at"}}
    if _canonical_hash(core) != plan.get("plan_sha256"):
        raise Phase79Error("rollout_plan_integrity_failed")
    if plan.get("safety", {}).get("active_bank_write") is not False or plan.get("safety", {}).get("production_activation") is not False:
        raise Phase79Error("rollout_plan_safety_flags_invalid")
    seen = set()
    for item in plan.get("items", []):
        key = item.get("stable_key")
        if not key or key in seen or item.get("state") not in ALLOWED_STATES:
            raise Phase79Error("rollout_plan_item_invalid")
        seen.add(key)


def build_operations_dashboard(plan: Mapping[str, Any], *, observed_events: Iterable[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """Summarize progress and exceptions from an immutable plan plus event stream."""
    validate_rollout_plan(plan)
    counts = {state: 0 for state in sorted(ALLOWED_STATES)}
    errors: dict[str, int] = {}
    attempts = 0
    items = {item["document_id"]: dict(item) for item in plan.get("items", [])}
    event_count = 0
    for event in observed_events:
        event_count += 1
        document_id = str(event.get("document_id") or "")
        if document_id in items:
            if event.get("state") in ALLOWED_STATES:
                items[document_id]["state"] = event["state"]
            if isinstance(event.get("attempts"), int) and not isinstance(event.get("attempts"), bool):
                items[document_id]["attempts"] = max(0, event["attempts"])
        code = event.get("error_code")
        if code:
            errors[str(code)] = errors.get(str(code), 0) + 1
    for item in items.values():
        counts[item["state"]] += 1
        attempts += int(item.get("attempts", 0))
        code = item.get("last_error_code")
        if code:
            errors[str(code)] = errors.get(str(code), 0) + 1
    total = len(plan.get("items", []))
    done = counts["completed"]
    return {
        "schema_version": SCHEMA_VERSION, "rollout_id": plan["rollout_id"],
        "planned_documents": total, "state_counts": counts,
        "completion_ratio": round(done / total, 6) if total else 0.0,
        "attempt_count": attempts, "observed_event_count": event_count,
        "error_counts": dict(sorted(errors.items())),
        "deferred_count": len(plan.get("deferred", [])),
        "rejected_count": len(plan.get("rejected", [])),
        "operational_status": "attention_required" if errors or counts["blocked"] else "planned_or_in_progress",
        "active_bank_modified": False, "production_activation": False,
    }


def create_recovery_checkpoint(plan: Mapping[str, Any], *, event_sequence: int = 0,
                               last_stable_event_id: str | None = None) -> dict[str, Any]:
    """Create a resumability marker; it never mutates item states or performs work."""
    validate_rollout_plan(plan)
    if isinstance(event_sequence, bool) or not isinstance(event_sequence, int) or event_sequence < 0:
        raise Phase79Error("event_sequence_must_be_non_negative_integer")
    core = {"schema_version": SCHEMA_VERSION, "rollout_id": plan["rollout_id"],
            "plan_sha256": plan["plan_sha256"], "event_sequence": event_sequence,
            "last_stable_event_id": last_stable_event_id,
            "resume_mode": "reconcile_from_last_committed_event",
            "requires_event_log_replay": True,
            "safety": {"automatic_retry": False, "network_access": False,
                       "active_bank_write": False, "production_activation": False}}
    return {**core, "checkpoint_sha256": _canonical_hash(core), "created_at": _utc_now()}


def validate_recovery_checkpoint(plan: Mapping[str, Any], checkpoint: Mapping[str, Any]) -> bool:
    validate_rollout_plan(plan)
    core = {k: v for k, v in checkpoint.items() if k not in {"checkpoint_sha256", "created_at"}}
    return bool(
        checkpoint.get("schema_version") == SCHEMA_VERSION
        and checkpoint.get("rollout_id") == plan.get("rollout_id")
        and checkpoint.get("plan_sha256") == plan.get("plan_sha256")
        and checkpoint.get("resume_mode") == "reconcile_from_last_committed_event"
        and checkpoint.get("requires_event_log_replay") is True
        and checkpoint.get("safety", {}).get("active_bank_write") is False
        and checkpoint.get("safety", {}).get("production_activation") is False
        and _canonical_hash(core) == checkpoint.get("checkpoint_sha256")
    )


def assess_activation_readiness(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Assess prerequisites only; never activate or grant legal authority.

    Required evidence keys are booleans supplied by an operator/release process.
    Missing, false, or non-boolean values fail closed.
    """
    required = (
        "source_registry_reviewed", "official_source_evidence_verified",
        "real_pdf_sample_validated", "human_review_completed",
        "golden_query_labels_supplied", "search_metrics_accepted",
        "backup_restore_drill_passed", "rollback_drill_passed",
        "security_review_passed", "operator_and_reviewer_separation_confirmed",
        "explicit_release_approval_recorded",
    )
    missing, failed = [], []
    for key in required:
        value = evidence.get(key)
        if not isinstance(value, bool):
            missing.append(key)
        elif value is not True:
            failed.append(key)
    ready = not missing and not failed
    return {
        "schema_version": SCHEMA_VERSION, "assessment": "activation_readiness_only",
        "readiness_status": "prerequisites_recorded" if ready else "not_ready",
        "required_checks": list(required), "missing_checks": missing,
        "failed_checks": failed,
        "production_activation_performed": False,
        "active_bank_write_performed": False,
        "legal_validity_or_force_determined": False,
        "human_release_authority_still_required": True,
        "note": "A ready result is not an activation command; production release remains a separate authorized operation.",
    }


def write_json_atomic(payload: Mapping[str, Any], destination: str | Path) -> Path:
    """Persist an operational artifact atomically to an explicit operator path."""
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(dict(payload), stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return path
