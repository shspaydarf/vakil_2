# -*- coding: utf-8 -*-
"""Phase 10.2.5: bounded maintenance-cycle wrapper and operational report.

This is an invokable runner, not an installed/active scheduler. Discovery and
all processing stages are injected adapters. Active-bank import remains opt-in.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .autonomous_orchestrator import run_ingestion_cycle
from .autonomous_maintenance import schedule_config


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(dict(payload), stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def scheduler_readiness(*, official_adapters_verified: bool,
                        runtime_connectivity_verified: bool,
                        recovery_drill_passed: bool,
                        bank_import_audited: bool = False) -> dict[str, Any]:
    """Report activation prerequisites; never enables the scheduler itself."""
    config = schedule_config()
    checks = {
        "official_adapters_verified": official_adapters_verified is True,
        "runtime_connectivity_verified": runtime_connectivity_verified is True,
        "recovery_drill_passed": recovery_drill_passed is True,
        "bank_import_audited": bank_import_audited is True,
    }
    return {
        "schedule": config,
        "checks": checks,
        "ready_for_scheduled_pilot": all(checks.values()),
        "scheduler_enabled": False,
        "activation_performed": False,
    }


def run_maintenance_cycle(*, discover: Callable[[], Iterable[Mapping[str, Any]]],
                          acquire: Callable[[dict[str, Any]], Mapping[str, Any]],
                          extract: Callable[[dict[str, Any]], Mapping[str, Any]],
                          validate: Callable[[dict[str, Any]], Mapping[str, Any]],
                          state_path: str | Path, report_path: str | Path,
                          import_document: Callable[[dict[str, Any]], Mapping[str, Any]] | None = None,
                          allow_bank_import: bool = False,
                          max_candidates: int = 100, max_pages: int = 20) -> dict[str, Any]:
    """Run one explicitly invoked cycle; default behavior is dry-run/no bank writes."""
    if import_document is not None and allow_bank_import is not True:
        raise ValueError("explicit_bank_import_authorization_required")
    started = datetime.now(timezone.utc).isoformat()
    report_file = Path(report_path)
    try:
        candidates = list(discover())
        cycle = run_ingestion_cycle(
            candidates, state_path=state_path, acquire=acquire, extract=extract,
            validate=validate, import_document=import_document,
            max_candidates=max_candidates, max_pages=max_pages,
        )
        result = {
            "runner_version": "10.2.5",
            "started_at": started,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "discovery_succeeded": True,
            "discovered_count": len(candidates),
            "cycle": cycle,
            "bank_import_authorized": allow_bank_import is True,
            "scheduler_enabled": False,
            "live_source_connectivity_proven": False,
            "legal_validity_proven": False,
            # The runner cannot infer the target of an injected import callback.
            # Report unknown rather than mislabeling sandbox writes as active-bank writes.
            "bank_import_callback_executed": bool(cycle.get("imported", 0)),
            "active_bank_changed": False if import_document is None else None,
            "active_bank_change_verified": False,
        }
    except Exception as exc:
        result = {
            "runner_version": "10.2.5",
            "started_at": started,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "discovery_succeeded": False,
            "error_type": type(exc).__name__,
            "error": str(exc)[:240],
            "bank_import_authorized": False,
            "scheduler_enabled": False,
            "live_source_connectivity_proven": False,
            "legal_validity_proven": False,
            "active_bank_changed": False,
        }
    _atomic_json(report_file, result)
    result["report_path"] = str(report_file)
    return result
