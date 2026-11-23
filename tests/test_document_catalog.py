import json
import pytest

from legal_bot.ingestion.document_catalog import DocumentCatalog, DocumentRecord, catalog_policy_summary
from legal_bot.ingestion.source_registry import SourceRecord, SourceRegistry


def primary_source():
    return SourceRecord.from_dict({
        "source_id": "majles_rc", "display_name": "مجلس", "publisher": "مجلس شورای اسلامی", "jurisdiction": "IR",
        "authority_level": "official_primary", "document_types": ["law", "amendment"],
        "allowed_hosts": ["rc.majlis.ir"], "canonical_roots": ["https://rc.majlis.ir/fa/law"],
        "access_mode": "polite_public_read", "status": "verified",
        "verification": {"reviewer_id": "human-1", "reviewed_at": "2026-11-01T10:00:00Z",
                          "evidence_ref": "evidence-1", "evidence_sha256": "a" * 64}
    })


def record(**updates):
    raw = {"source_id": "majles_rc", "document_type": "law", "title": "قانون آزمایشی",
           "external_id": "law-123", "document_url": "https://rc.majlis.ir/fa/law/123",
           "approval_date": "1400-02-03", "issuer": "مجلس", "content_sha256": "b" * 64}
    raw.update(updates)
    return raw


def test_catalog_starts_empty_and_policy_is_safe(tmp_path):
    cat = DocumentCatalog(tmp_path / "catalog.json")
    assert cat.load()["catalog_version"] == 0
    policy = catalog_policy_summary()
    assert policy["network_discovery"] is False and policy["active_bank_write"] is False


def test_ingest_official_document_and_stable_id(tmp_path):
    reg = SourceRegistry(tmp_path / "sources.json")
    reg.upsert(primary_source(), actor_id="admin", reason="evidence checked")
    cat = DocumentCatalog(tmp_path / "catalog.json", reg)
    result = cat.ingest([record()], actor_id="admin", reason="manual inventory")
    row = cat.list_documents()[0]
    assert result["added"] == 1 and row["discovery_status"] == "discovered"
    assert row["document_id"] == DocumentRecord.from_dict(record()).document_id


def test_unknown_source_rejected_when_registry_is_attached(tmp_path):
    cat = DocumentCatalog(tmp_path / "catalog.json", SourceRegistry(tmp_path / "sources.json"))
    result = cat.ingest([record()], actor_id="admin", reason="test")
    assert result["rejected"] == 1 and result["total_documents"] == 0


def test_url_must_be_allowed_by_registered_source(tmp_path):
    reg = SourceRegistry(tmp_path / "sources.json")
    reg.upsert(primary_source(), actor_id="admin", reason="evidence checked")
    cat = DocumentCatalog(tmp_path / "catalog.json", reg)
    result = cat.ingest([record(document_url="https://evil.example/law/123")], actor_id="admin", reason="test")
    assert result["rejected"] == 1


def test_secondary_or_unverified_source_is_quarantined(tmp_path):
    reg = SourceRegistry(tmp_path / "sources.json")
    secondary = SourceRecord.from_dict({"source_id": "ekhtebar", "display_name": "اختبار", "publisher": "اختبار", "jurisdiction": "IR", "authority_level": "secondary"})
    reg.upsert(secondary, actor_id="admin", reason="catalog source")
    cat = DocumentCatalog(tmp_path / "catalog.json", reg)
    item = record(source_id="ekhtebar", document_url=None, external_id="ekhtebar-1")
    result = cat.ingest([item], actor_id="admin", reason="discovery")
    assert result["quarantined"] == 1
    assert cat.list_documents()[0]["discovery_status"] == "quarantined"


def test_exact_content_hash_duplicates_are_grouped_not_merged(tmp_path):
    reg = SourceRegistry(tmp_path / "sources.json")
    reg.upsert(primary_source(), actor_id="admin", reason="evidence checked")
    cat = DocumentCatalog(tmp_path / "catalog.json", reg)
    second = record(external_id="law-124", document_url="https://rc.majlis.ir/fa/law/124")
    result = cat.ingest([record(), second], actor_id="admin", reason="inventory")
    assert result["added"] == 2 and result["duplicate_groups"] == 1
    assert len(cat.list_documents()) == 2


def test_identical_import_is_skipped_and_conflict_is_rejected(tmp_path):
    reg = SourceRegistry(tmp_path / "sources.json")
    reg.upsert(primary_source(), actor_id="admin", reason="evidence checked")
    cat = DocumentCatalog(tmp_path / "catalog.json", reg)
    cat.ingest([record()], actor_id="admin", reason="first")
    same = cat.ingest([record()], actor_id="admin", reason="repeat")
    changed = cat.ingest([record(title="عنوان متفاوت")], actor_id="admin", reason="conflict")
    assert same["duplicates_skipped"] == 1
    assert changed["rejected"] == 1


def test_stale_catalog_version_rejected(tmp_path):
    cat = DocumentCatalog(tmp_path / "catalog.json")
    cat.ingest([record(document_url=None)], actor_id="admin", reason="first")
    with pytest.raises(RuntimeError, match="catalog_version_conflict"):
        cat.ingest([record(external_id="law-124", document_url=None)], actor_id="admin", reason="stale", expected_version=0)


def test_invalid_date_hash_and_url_are_rejected():
    with pytest.raises(ValueError, match="dates"):
        DocumentRecord.from_dict(record(approval_date="yesterday"))
    with pytest.raises(ValueError, match="SHA-256"):
        DocumentRecord.from_dict(record(content_sha256="bad"))
    with pytest.raises(ValueError, match="HTTPS"):
        DocumentRecord.from_dict(record(document_url="http://example.org/a"))


def test_filtered_listing_and_audit(tmp_path):
    cat = DocumentCatalog(tmp_path / "catalog.json")
    cat.ingest([record(document_url=None)], actor_id="admin", reason="manual")
    assert len(cat.list_documents(source_id="majles_rc", document_type="law")) == 1
    data = json.loads((tmp_path / "catalog.json").read_text(encoding="utf-8"))
    assert data["audit"][-1]["action"] == "catalog_ingest"


def test_catalog_rejects_unregistered_discovery_or_asset_url(tmp_path):
    import hashlib
    import pytest
    from legal_bot.ingestion.source_registry import SourceRecord, SourceRegistry

    registry = SourceRegistry(tmp_path / "registry.json")
    registry.upsert(SourceRecord(
        source_id="official", display_name="Official", publisher="Issuer", jurisdiction="IR",
        authority_level="unverified", document_types=("law",),
        allowed_hosts=("laws.example.ir",), canonical_roots=("https://laws.example.ir/",),
        access_mode="disabled", status="unverified",
    ), actor_id="test", reason="fixture")
    catalog = DocumentCatalog(tmp_path / "catalog.json", source_registry=registry)
    record = {
        "source_id": "official", "document_type": "law", "title": "نمونه",
        "external_id": "L-2", "document_url": "https://laws.example.ir/law/2",
        "discovery_page_url": "https://evil.example/page",
    }
    result = catalog.ingest([record], actor_id="test", reason="reject unsafe provenance")
    assert result["rejected"] == 1
    assert catalog.list_documents() == []
