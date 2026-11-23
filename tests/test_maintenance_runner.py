import hashlib
import json
import pytest
from legal_bot.ingestion.maintenance_runner import run_maintenance_cycle, scheduler_readiness


def _candidate():
    return {"source_id": "official", "document_kind": "law", "issuer": "مجلس",
            "official_number": "77", "approval_date": "1402-01-01", "title": "قانون آزمایشی",
            "external_id": "77", "source_url": "https://example.gov.ir/doc/77"}


def _adapters():
    def acquire(row): return {"page_count": 2, "local_path": "synthetic://pdf"}
    def extract(row): return {"content_sha256": hashlib.sha256(b"synthetic text").hexdigest(), "text": "متن آزمایشی"}
    def validate(row): return {"accepted": True, "primary_source_verified": True}
    return acquire, extract, validate


def test_runner_executes_discovery_to_ready_state_without_import(tmp_path):
    a, e, v = _adapters()
    report = run_maintenance_cycle(discover=lambda: [_candidate()], acquire=a, extract=e, validate=v,
        state_path=tmp_path/"state.json", report_path=tmp_path/"report.json")
    assert report["discovery_succeeded"] is True
    assert report["cycle"]["processed"] == 1
    assert report["cycle"]["imported"] == 0
    assert report["active_bank_changed"] is False
    assert report["scheduler_enabled"] is False
    assert json.loads((tmp_path/"report.json").read_text())["runner_version"] == "10.2.5"


def test_runner_fails_closed_on_discovery_error(tmp_path):
    a, e, v = _adapters()
    report = run_maintenance_cycle(discover=lambda: (_ for _ in ()).throw(OSError("offline")),
        acquire=a, extract=e, validate=v, state_path=tmp_path/"state.json", report_path=tmp_path/"report.json")
    assert report["discovery_succeeded"] is False
    assert report["active_bank_changed"] is False


def test_import_requires_explicit_authorization(tmp_path):
    a, e, v = _adapters()
    with pytest.raises(ValueError, match="explicit_bank_import_authorization_required"):
        run_maintenance_cycle(discover=lambda: [], acquire=a, extract=e, validate=v,
            state_path=tmp_path/"state.json", report_path=tmp_path/"report.json",
            import_document=lambda row: {"imported": True})


def test_scheduler_readiness_never_enables_schedule_automatically():
    result = scheduler_readiness(official_adapters_verified=True, runtime_connectivity_verified=True,
                                recovery_drill_passed=True, bank_import_audited=True)
    assert result["ready_for_scheduled_pilot"] is True
    assert result["scheduler_enabled"] is False
    assert result["schedule"]["enabled"] is False


def test_scheduler_not_ready_when_any_prerequisite_missing():
    result = scheduler_readiness(official_adapters_verified=True, runtime_connectivity_verified=False,
                                recovery_drill_passed=True)
    assert result["ready_for_scheduled_pilot"] is False
