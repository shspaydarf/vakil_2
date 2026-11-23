import hashlib

from legal_bot.ingestion.catalog_download_bridge import CatalogDownloadBridge
from legal_bot.ingestion.document_catalog import DocumentCatalog, DocumentRecord
from legal_bot.ingestion.download_queue import DownloadQueue
from legal_bot.ingestion.source_registry import SourceRecord, SourceRegistry


def _registered_registry(tmp_path, *, verified=True):
    registry = SourceRegistry(tmp_path / "sources.json")
    verification = ({
        "reviewer_id": "reviewer-test", "reviewed_at": "2026-11-23",
        "evidence_ref": "fixture:source-policy", "evidence_sha256": hashlib.sha256(b"evidence").hexdigest(),
    } if verified else {})
    registry.upsert(SourceRecord(
        source_id="majles_rc", display_name="مرکز پژوهش‌های مجلس",
        publisher="مرکز پژوهش‌های مجلس شورای اسلامی", jurisdiction="IR",
        authority_level="official_primary" if verified else "unverified",
        document_types=("law",), allowed_hosts=("rc.majlis.ir",),
        canonical_roots=("https://rc.majlis.ir/fa/law",),
        access_mode="polite_public_read" if verified else "disabled",
        status="verified" if verified else "unverified", verification=verification,
    ), actor_id="test", reason="test fixture source policy")
    return registry


def _catalog(tmp_path, registry, *, asset=True):
    catalog = DocumentCatalog(tmp_path / "catalog.json", source_registry=registry)
    record = DocumentRecord(
        source_id="majles_rc", document_type="law", title="قانون نمونه",
        external_id="123", document_url="https://rc.majlis.ir/fa/law/show/123",
        document_family="laws", source_role="official_primary",
        source_name="مرکز پژوهش‌های مجلس", source_record_id="123",
        discovery_page_url="https://rc.majlis.ir/fa/law/show/123",
        asset_url="https://rc.majlis.ir/fa/law/files/123.pdf" if asset else None,
        connector_document_type="parliamentary_law_record",
    )
    result = catalog.ingest([record], actor_id="test", reason="fixture catalog record")
    return catalog, result


def test_verified_catalog_asset_enters_queue_and_preserves_family(tmp_path):
    registry = _registered_registry(tmp_path)
    catalog, _ = _catalog(tmp_path, registry)
    queue = DownloadQueue(tmp_path / "queue.json", allowed_hosts={"rc.majlis.ir"})
    bridge = CatalogDownloadBridge(registry=registry, queue=queue)
    result = bridge.enqueue_catalog(catalog)
    assert result["added"] == 1
    row = queue.list_items(state="queued")[0]["candidate"]
    assert row["document_family"] == "laws"
    assert row["catalog_document_id"]
    assert result["downloads_performed"] is False


def test_quarantined_catalog_record_never_enters_queue(tmp_path):
    registry = _registered_registry(tmp_path, verified=False)
    catalog, _ = _catalog(tmp_path, registry)
    queue = DownloadQueue(tmp_path / "queue.json", allowed_hosts={"rc.majlis.ir"})
    result = CatalogDownloadBridge(registry=registry, queue=queue).enqueue_catalog(catalog)
    assert result["added"] == 0
    assert result["skipped"]["not_eligible_status"] == 1


def test_catalog_record_without_direct_asset_is_not_queued(tmp_path):
    registry = _registered_registry(tmp_path)
    catalog, _ = _catalog(tmp_path, registry, asset=False)
    queue = DownloadQueue(tmp_path / "queue.json", allowed_hosts={"rc.majlis.ir"})
    result = CatalogDownloadBridge(registry=registry, queue=queue).enqueue_catalog(catalog)
    assert result["added"] == 0
    assert result["skipped"]["no_direct_asset"] == 1


def test_repeated_catalog_queueing_is_idempotent_by_catalog_identity(tmp_path):
    registry = _registered_registry(tmp_path)
    catalog, _ = _catalog(tmp_path, registry)
    queue = DownloadQueue(tmp_path / "queue.json", allowed_hosts={"rc.majlis.ir"})
    bridge = CatalogDownloadBridge(registry=registry, queue=queue)
    first = bridge.enqueue_catalog(catalog)
    second = bridge.enqueue_catalog(catalog)
    assert first["added"] == 1
    assert second["duplicates_skipped"] == 1
    assert len(queue.list_items()) == 1


def test_queue_host_allowlist_is_independent_fail_closed_gate(tmp_path):
    registry = _registered_registry(tmp_path)
    catalog, _ = _catalog(tmp_path, registry)
    queue = DownloadQueue(tmp_path / "queue.json", allowed_hosts={"other.example"})
    result = CatalogDownloadBridge(registry=registry, queue=queue).enqueue_catalog(catalog)
    assert result["added"] == 0
    assert result["skipped"]["queue_host_not_allowlisted"] == 1


def test_revoked_source_policy_blocks_previously_discovered_asset(tmp_path):
    registry = _registered_registry(tmp_path)
    catalog, _ = _catalog(tmp_path, registry)
    # Revoke public-read permission after discovery but before queueing.
    registry.upsert(SourceRecord(
        source_id="majles_rc", display_name="مرکز پژوهش‌های مجلس",
        publisher="مرکز پژوهش‌های مجلس شورای اسلامی", jurisdiction="IR",
        authority_level="unverified", document_types=("law",),
        allowed_hosts=("rc.majlis.ir",),
        canonical_roots=("https://rc.majlis.ir/fa/law",),
        access_mode="disabled", status="unverified", verification={},
    ), actor_id="test", reason="revoke access for test")
    queue = DownloadQueue(tmp_path / "queue.json", allowed_hosts={"rc.majlis.ir"})
    result = CatalogDownloadBridge(registry=registry, queue=queue).enqueue_catalog(catalog)
    assert result["added"] == 0
    assert result["skipped"]["source_policy_denied"] == 1
