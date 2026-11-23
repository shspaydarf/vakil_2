"""Phase 10.3.6: recovery drill and scheduler activation guardrails.

All tests use local temporary state and injected adapters. No network, live
scheduler, or active-bank write is performed.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from legal_bot.ingestion.autonomous_orchestrator import run_ingestion_cycle
from legal_bot.ingestion.autonomous_maintenance import schedule_config
from legal_bot.ingestion.maintenance_runner import scheduler_readiness


def _candidate(external_id: str, digest: str) -> dict:
    return {
        "source_id": "synthetic_fixture",
        "document_kind": "law",
        "issuer": "TEST",
        "official_number": external_id,
        "approval_date": "1405-01-01",
        "title": f"سند آزمایشی {external_id}",
        "external_id": external_id,
        "source_url": f"https://fixture.invalid/{external_id}",
        "content_sha256": digest,
    }


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_crash_after_checkpoint_resumes_without_reprocessing_completed_item(tmp_path: Path):
    state = tmp_path / "state.json"
    a_text, b_text = "synthetic A", "synthetic B"
    a, b = _candidate("A", _digest(a_text)), _candidate("B", _digest(b_text))
    calls = {"acquire": [], "extract": []}

    def acquire(row):
        calls["acquire"].append(row["external_id"])
        return {"page_count": 1}

    def extract_first_run(row):
        calls["extract"].append(row["external_id"])
        if row["external_id"] == "B":
            raise SystemExit("simulated_process_termination")
        return {"text": a_text, "content_sha256": _digest(a_text), "page_count": 1}

    validate = lambda row: {"accepted": True, "primary_source_verified": True}

    with pytest.raises(SystemExit, match="simulated_process_termination"):
        run_ingestion_cycle([a, b], state_path=state, acquire=acquire,
                            extract=extract_first_run, validate=validate)

    checkpoint = json.loads(state.read_text(encoding="utf-8"))
    assert len(checkpoint["documents"]) == 1
    assert next(iter(checkpoint["documents"].values()))["content_sha256"] == _digest(a_text)

    def extract_after_restart(row):
        calls["extract"].append(row["external_id"])
        text = a_text if row["external_id"] == "A" else b_text
        return {"text": text, "content_sha256": _digest(text), "page_count": 1}

    resumed = run_ingestion_cycle([a, b], state_path=state, acquire=acquire,
                                  extract=extract_after_restart, validate=validate)
    assert resumed["duplicates"] == 1
    assert resumed["processed"] == 1
    assert calls["acquire"].count("A") == 1
    assert calls["acquire"].count("B") == 2  # interrupted item is retried safely
    final = json.loads(state.read_text(encoding="utf-8"))
    assert len(final["documents"]) == 2


def test_schedule_is_biweekly_tehran_monday_0900_and_remains_disabled():
    config = schedule_config()
    assert config["timezone"] == "Asia/Tehran"
    assert config["weekday"] == "MO"
    assert config["interval_weeks"] == 2
    assert config["local_time"] == "09:00"
    assert config["max_total_pdf_pages"] == 20
    assert config["enabled"] is False


def test_scheduler_readiness_is_not_a_scheduler_activation_switch():
    result = scheduler_readiness(
        official_adapters_verified=True,
        runtime_connectivity_verified=True,
        recovery_drill_passed=True,
        bank_import_audited=True,
    )
    assert result["ready_for_scheduled_pilot"] is True
    assert result["scheduler_enabled"] is False
    assert result["activation_performed"] is False
    assert result["schedule"]["enabled"] is False


def test_scheduler_readiness_fails_closed_when_any_gate_is_missing():
    for field in ("official", "runtime", "recovery", "bank"):
        result = scheduler_readiness(
            official_adapters_verified=field != "official",
            runtime_connectivity_verified=field != "runtime",
            recovery_drill_passed=field != "recovery",
            bank_import_audited=field != "bank",
        )
        assert result["ready_for_scheduled_pilot"] is False
        assert result["scheduler_enabled"] is False
