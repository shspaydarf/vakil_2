from dataclasses import asdict
import hashlib
import json

import pytest

from legal_bot.ingestion.source_registry import SourceRecord, SourceRegistry, registry_policy_summary


def verified_record(**overrides):
    raw = {
        "source_id": "majles_rc", "display_name": "مرکز پژوهش‌های مجلس",
        "publisher": "مرکز پژوهش‌های مجلس شورای اسلامی", "jurisdiction": "IR",
        "authority_level": "official_primary", "document_types": ["law", "amendment"],
        "allowed_hosts": ["rc.majlis.ir"],
        "canonical_roots": ["https://rc.majlis.ir/fa/law"],
        "access_mode": "polite_public_read", "respect_robots_txt": True,
        "min_request_interval_seconds": 5, "max_pages_per_run": 2,
        "status": "verified",
        "verification": {"reviewer_id": "reviewer-1", "reviewed_at": "2026-11-01T10:00:00Z",
                          "evidence_ref": "manual-source-review-001", "evidence_sha256": "a" * 64},
    }
    raw.update(overrides)
    return SourceRecord.from_dict(raw)


def test_registry_starts_empty_and_network_disabled(tmp_path):
    registry = SourceRegistry(tmp_path / "sources.json")
    assert registry.load() == {"schema_version": "7.2", "registry_version": 0, "sources": {}, "audit": []}
    assert registry_policy_summary()["default_network_access"] is False


def test_unverified_is_default_and_cannot_be_primary():
    raw = {"source_id": "test_source", "display_name": "Test", "publisher": "Test publisher", "jurisdiction": "IR"}
    record = SourceRecord.from_dict(raw)
    assert record.authority_level == "unverified"
    assert record.status == "unverified"
    with pytest.raises(ValueError, match="official_primary"):
        SourceRecord.from_dict(raw | {"authority_level": "official_primary"})


def test_verified_primary_requires_human_evidence():
    raw = asdict(verified_record())
    raw["verification"] = {"reviewer_id": "x"}
    with pytest.raises(ValueError, match="requires reviewer"):
        SourceRecord.from_dict(raw)


def test_exact_host_and_root_path_allowlist():
    record = verified_record()
    assert record.permits_url("https://rc.majlis.ir/fa/law/show/123")
    assert not record.permits_url("https://evilrc.majlis.ir/fa/law/show/123")
    assert not record.permits_url("http://rc.majlis.ir/fa/law/show/123")
    assert not record.permits_url("https://rc.majlis.ir.evil.test/fa/law/show/123")
    assert not record.permits_url("https://rc.majlis.ir/fa/other/123")
    assert not record.permits_url("https://user@rc.majlis.ir/fa/law/show/123")


def test_public_read_requires_verified_source_and_hosts():
    raw = asdict(verified_record())
    raw["status"] = "unverified"
    with pytest.raises(ValueError, match="verified status"):
        SourceRecord.from_dict(raw)


def test_canonical_root_must_be_https_and_allowed_host():
    raw = asdict(verified_record())
    raw["canonical_roots"] = ["https://other.example/laws"]
    with pytest.raises(ValueError, match="exact allowed host"):
        SourceRecord.from_dict(raw)


def test_registry_upsert_is_versioned_and_audited(tmp_path):
    registry = SourceRegistry(tmp_path / "registry.json")
    result = registry.upsert(verified_record(), actor_id="admin", reason="manual evidence review", expected_version=0)
    assert result["registry_version"] == 1
    assert result["audit"][0]["action"] == "create"
    assert result["audit"][0]["current_sha256"]
    assert registry.get("majles_rc").status == "verified"
    loaded = json.loads((tmp_path / "registry.json").read_text(encoding="utf-8"))
    assert loaded["registry_version"] == 1


def test_registry_rejects_stale_version(tmp_path):
    registry = SourceRegistry(tmp_path / "registry.json")
    registry.upsert(verified_record(), actor_id="admin", reason="first", expected_version=0)
    with pytest.raises(RuntimeError, match="registry_version_conflict"):
        registry.upsert(verified_record(notes="change"), actor_id="admin", reason="stale", expected_version=0)


def test_registry_requires_actor_and_reason(tmp_path):
    with pytest.raises(ValueError, match="actor_id and reason"):
        SourceRegistry(tmp_path / "registry.json").upsert(verified_record(), actor_id="", reason="x")


def test_invalid_host_patterns_are_rejected():
    raw = asdict(verified_record())
    raw["allowed_hosts"] = ["*.majlis.ir"]
    with pytest.raises(ValueError, match="exact DNS"):
        SourceRecord.from_dict(raw)
