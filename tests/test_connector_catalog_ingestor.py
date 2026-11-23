import hashlib

import pytest

from legal_bot.ingestion.connector_catalog_ingestor import ConnectorCatalogIngestor
from legal_bot.ingestion.connectors.majles_rc import MajlesResearchCenterConnector
from legal_bot.ingestion.document_catalog import DocumentCatalog
from legal_bot.ingestion.source_registry import SourceRecord, SourceRegistry


def _source(tmp_path, *, status="verified", authority="official_primary", access="polite_public_read"):
    verification = ({
        "reviewer_id": "reviewer-test", "reviewed_at": "2026-11-23",
        "evidence_ref": "fixture:approved-source-record",
        "evidence_sha256": hashlib.sha256(b"source evidence fixture").hexdigest(),
    } if status == "verified" else {})
    return SourceRecord(
        source_id="majles_rc", display_name="مرکز پژوهش‌های مجلس",
        publisher="مرکز پژوهش‌های مجلس شورای اسلامی", jurisdiction="IR",
        authority_level=authority, document_types=("law",),
        allowed_hosts=("rc.majlis.ir",),
        canonical_roots=("https://rc.majlis.ir/fa/law",),
        access_mode=access, status=status, verification=verification,
    )


def _setup(tmp_path, **source_kwargs):
    registry = SourceRegistry(tmp_path / "source_registry.json")
    registry.upsert(_source(tmp_path, **source_kwargs), actor_id="test", reason="fixture registration")
    catalog = DocumentCatalog(tmp_path / "document_catalog.json", source_registry=registry)
    ingestor = ConnectorCatalogIngestor(
        registry=registry, catalog=catalog, checkpoint_path=str(tmp_path / "discovery_checkpoints.json")
    )
    return registry, catalog, ingestor


_HTML = '''<html><body><a href="/fa/law/show/12345">قانون نمونه ۱۴۰۲</a></body></html>'''
_PAGE = "https://rc.majlis.ir/fa/law/archive"


def test_verified_primary_connector_flows_to_catalog_and_checkpoint(tmp_path):
    _, catalog, ingestor = _setup(tmp_path)
    result = ingestor.ingest_saved_html(
        MajlesResearchCenterConnector(), _HTML, _PAGE, category="laws", next_cursor="fixture-page-2"
    )
    assert result["added"] == 1
    assert result["candidate_count"] == 1
    assert result["network_calls_performed"] is False
    assert result["active_bank_writes"] is False
    rows = catalog.list_documents(source_id="majles_rc")
    assert len(rows) == 1
    assert rows[0]["discovery_status"] == "discovered"
    assert rows[0]["record"]["document_family"] == "laws"
    assert rows[0]["record"]["source_record_id"] == "12345"
    assert rows[0]["record"]["discovery_page_url"] == _PAGE


def test_unverified_source_can_be_inventoried_but_is_quarantined(tmp_path):
    _, catalog, ingestor = _setup(tmp_path, status="unverified", authority="unverified", access="disabled")
    result = ingestor.ingest_saved_html(MajlesResearchCenterConnector(), _HTML, _PAGE, category="laws")
    assert result["added"] == 1
    assert result["network_permitted"] is False
    rows = catalog.list_documents(source_id="majles_rc")
    assert rows[0]["discovery_status"] == "quarantined"


def test_same_connector_batch_retry_is_idempotent(tmp_path):
    _, catalog, ingestor = _setup(tmp_path)
    ingestor.ingest_saved_html(MajlesResearchCenterConnector(), _HTML, _PAGE, category="laws")
    result = ingestor.ingest_saved_html(MajlesResearchCenterConnector(), _HTML, _PAGE, category="laws")
    assert result["duplicates_skipped"] == 1
    assert len(catalog.list_documents(source_id="majles_rc")) == 1


def test_unknown_source_is_rejected_before_catalog_mutation(tmp_path):
    registry = SourceRegistry(tmp_path / "registry.json")
    catalog = DocumentCatalog(tmp_path / "catalog.json", source_registry=registry)
    ingestor = ConnectorCatalogIngestor(registry=registry, catalog=catalog,
                                        checkpoint_path=str(tmp_path / "checkpoints.json"))
    with pytest.raises(ValueError, match="source_not_registered"):
        ingestor.ingest_saved_html(MajlesResearchCenterConnector(), _HTML, _PAGE, category="laws")
    assert catalog.list_documents() == []


def test_unapproved_host_and_root_are_rejected(tmp_path):
    _, catalog, ingestor = _setup(tmp_path)
    with pytest.raises(ValueError, match="discovery_page_not_allowed"):
        ingestor.ingest_saved_html(
            MajlesResearchCenterConnector(), _HTML,
            "https://evil.example/fa/law/archive", category="laws"
        )
    assert catalog.list_documents() == []


def test_secondary_source_is_cataloged_but_not_promoted_to_pipeline(tmp_path):
    _, catalog, ingestor = _setup(tmp_path, authority="secondary")
    result = ingestor.ingest_saved_html(MajlesResearchCenterConnector(), _HTML, _PAGE, category="laws")
    assert result["quarantined"] == 1
    assert catalog.list_documents(source_id="majles_rc")[0]["discovery_status"] == "quarantined"


def test_qavanin_connector_uses_same_registry_catalog_path(tmp_path):
    from pathlib import Path
    from legal_bot.ingestion.connectors import QavaninConnector

    fixture = Path(__file__).parent / "fixtures" / "ingestion" / "qavanin_search_results_sample.html"
    registry = SourceRegistry(tmp_path / "qavanin_registry.json")
    verification = {
        "reviewer_id": "reviewer-test", "reviewed_at": "2026-11-23",
        "evidence_ref": "fixture:qavanin-source-policy",
        "evidence_sha256": hashlib.sha256(b"qavanin source evidence").hexdigest(),
    }
    registry.upsert(SourceRecord(
        source_id="qavanin_national", display_name="Qavanin", publisher="Qavanin",
        jurisdiction="IR", authority_level="unverified", document_types=("law",),
        allowed_hosts=("qavanin.ir", "www.qavanin.ir"),
        canonical_roots=("https://qavanin.ir/",), access_mode="disabled",
        status="unverified", verification={},
    ), actor_id="test", reason="unverified fixture source registration")
    catalog = DocumentCatalog(tmp_path / "qavanin_catalog.json", source_registry=registry)
    ingestor = ConnectorCatalogIngestor(registry=registry, catalog=catalog,
                                        checkpoint_path=str(tmp_path / "qavanin_checkpoints.json"))
    result = ingestor.ingest_saved_html(QavaninConnector(), fixture.read_text(encoding="utf-8"),
                                        "https://qavanin.ir/", category="laws")
    assert result["candidate_count"] == 2
    assert result["added"] == 2
    rows = catalog.list_documents(source_id="qavanin_national")
    assert len(rows) == 2
    assert all(row["discovery_status"] == "quarantined" for row in rows)
    assert all(row["record"]["document_family"] == "laws" for row in rows)
