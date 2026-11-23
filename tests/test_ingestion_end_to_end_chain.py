import hashlib

from legal_bot.ingestion.catalog_download_bridge import CatalogDownloadBridge
from legal_bot.ingestion.connector_catalog_ingestor import ConnectorCatalogIngestor
from legal_bot.ingestion.connectors.majles_rc import MajlesResearchCenterConnector
from legal_bot.ingestion.document_catalog import DocumentCatalog
from legal_bot.ingestion.download_queue import DownloadQueue
from legal_bot.ingestion.source_registry import SourceRecord, SourceRegistry

PAGE = "https://rc.majlis.ir/fa/law/archive"
HTML_WITH_PDF = """
<html><body>
  <a href="/fa/law/show/12345">قانون نمونه ۱۴۰۲</a>
  <a href="/fa/law/files/12345.pdf">دریافت فایل قانون نمونه</a>
</body></html>
"""

def _source(*, verified=True):
    if verified:
        verification = {
            "reviewer_id": "e2e-reviewer", "reviewed_at": "2026-11-23",
            "evidence_ref": "fixture:e2e-approved-source",
            "evidence_sha256": hashlib.sha256(b"e2e source evidence").hexdigest(),
        }
        status, authority, access = "verified", "official_primary", "polite_public_read"
    else:
        verification = {}
        status, authority, access = "unverified", "unverified", "disabled"
    return SourceRecord(
        source_id="majles_rc", display_name="مرکز پژوهش‌های مجلس",
        publisher="مرکز پژوهش‌های مجلس شورای اسلامی", jurisdiction="IR",
        authority_level=authority, document_types=("law",),
        allowed_hosts=("rc.majlis.ir",),
        canonical_roots=("https://rc.majlis.ir/fa/law",),
        access_mode=access, status=status, verification=verification,
    )

def _stack(tmp_path, *, verified=True, queue_hosts=("rc.majlis.ir",)):
    registry = SourceRegistry(tmp_path / "source_registry.json")
    registry.upsert(_source(verified=verified), actor_id="e2e-test", reason="test source setup")
    catalog = DocumentCatalog(tmp_path / "document_catalog.json", source_registry=registry)
    ingestor = ConnectorCatalogIngestor(
        registry=registry, catalog=catalog,
        checkpoint_path=tmp_path / "discovery_checkpoints.json",
    )
    queue = DownloadQueue(tmp_path / "download_queue.json", allowed_hosts=queue_hosts)
    bridge = CatalogDownloadBridge(registry=registry, queue=queue)
    return registry, catalog, ingestor, queue, bridge

def test_full_connector_catalog_queue_path_with_direct_pdf(tmp_path):
    _, catalog, ingestor, queue, bridge = _stack(tmp_path)
    discovered = ingestor.ingest_saved_html(
        MajlesResearchCenterConnector(), HTML_WITH_PDF, PAGE,
        category="laws", next_cursor="page-2",
    )
    assert discovered["candidate_count"] == 2
    assert discovered["added"] == 2
    assert discovered["network_calls_performed"] is False
    assert discovered["downloads_performed"] is False
    assert discovered["active_bank_writes"] is False
    queued = bridge.enqueue_catalog(catalog, source_id="majles_rc")
    assert queued["catalog_rows_seen"] == 2
    assert queued["eligible_candidates"] == 1
    assert queued["added"] == 1
    assert queued["skipped"]["no_direct_asset"] == 1
    assert queued["downloads_performed"] is False
    item = queue.list_items(state="queued")[0]["candidate"]
    assert item["asset_url"] == "https://rc.majlis.ir/fa/law/files/12345.pdf"
    assert item["document_family"] == "laws"
    assert item["catalog_document_id"]

def test_restart_and_replay_do_not_duplicate_catalog_or_queue(tmp_path):
    _, catalog, ingestor, _, bridge = _stack(tmp_path)
    ingestor.ingest_saved_html(MajlesResearchCenterConnector(), HTML_WITH_PDF, PAGE, category="laws")
    assert bridge.enqueue_catalog(catalog)["added"] == 1
    registry2 = SourceRegistry(tmp_path / "source_registry.json")
    catalog2 = DocumentCatalog(tmp_path / "document_catalog.json", source_registry=registry2)
    ingestor2 = ConnectorCatalogIngestor(
        registry=registry2, catalog=catalog2,
        checkpoint_path=tmp_path / "discovery_checkpoints.json",
    )
    queue2 = DownloadQueue(tmp_path / "download_queue.json", allowed_hosts={"rc.majlis.ir"})
    bridge2 = CatalogDownloadBridge(registry=registry2, queue=queue2)
    replay = ingestor2.ingest_saved_html(
        MajlesResearchCenterConnector(), HTML_WITH_PDF, PAGE, category="laws", next_cursor="page-2",
    )
    assert replay["duplicates_skipped"] == 2
    second = bridge2.enqueue_catalog(catalog2)
    assert second["added"] == 0
    assert second["duplicates_skipped"] == 1
    assert len(queue2.list_items()) == 1
    assert len(catalog2.list_documents()) == 2

def test_unverified_source_is_quarantined_and_never_queued(tmp_path):
    _, catalog, ingestor, queue, bridge = _stack(tmp_path, verified=False)
    result = ingestor.ingest_saved_html(
        MajlesResearchCenterConnector(), HTML_WITH_PDF, PAGE, category="laws",
    )
    assert result["quarantined"] == 2
    assert bridge.enqueue_catalog(catalog)["added"] == 0
    assert queue.list_items() == []

def test_revoked_source_permission_blocks_previously_cataloged_asset(tmp_path):
    registry, catalog, ingestor, queue, bridge = _stack(tmp_path)
    ingestor.ingest_saved_html(
        MajlesResearchCenterConnector(), HTML_WITH_PDF, PAGE, category="laws",
    )
    source = registry.get("majles_rc")
    revoked = SourceRecord.from_dict({
        **source.__dict__, "status": "unverified", "authority_level": "unverified",
        "access_mode": "disabled", "verification": {},
    })
    registry.upsert(revoked, actor_id="e2e-reviewer", reason="permission revoked in test")
    queued = bridge.enqueue_catalog(catalog)
    assert queued["added"] == 0
    assert queued["skipped"]["source_policy_denied"] == 1
    assert queue.list_items() == []

def test_external_host_asset_is_ignored_by_connector(tmp_path):
    _, catalog, ingestor, queue, bridge = _stack(tmp_path)
    hostile_html = '<html><body><a href="https://evil.example/malicious.pdf">قانون جعلی</a></body></html>'
    result = ingestor.ingest_saved_html(
        MajlesResearchCenterConnector(), hostile_html, PAGE, category="laws",
    )
    assert result["candidate_count"] == 0
    assert catalog.list_documents() == []
    assert bridge.enqueue_catalog(catalog)["added"] == 0
    assert queue.list_items() == []

def test_queue_host_allowlist_is_independent_final_gate(tmp_path):
    _, catalog, ingestor, queue, bridge = _stack(
        tmp_path, verified=True, queue_hosts=("other.example",),
    )
    ingestor.ingest_saved_html(
        MajlesResearchCenterConnector(), HTML_WITH_PDF, PAGE, category="laws",
    )
    queued = bridge.enqueue_catalog(catalog)
    assert queued["added"] == 0
    assert queued["skipped"]["queue_host_not_allowlisted"] == 1
    assert queue.list_items() == []


def test_queue_retry_is_bounded_and_survives_restart(tmp_path):
    from datetime import datetime, timedelta, timezone

    _, catalog, ingestor, queue, bridge = _stack(tmp_path)
    ingestor.ingest_saved_html(
        MajlesResearchCenterConnector(), HTML_WITH_PDF, PAGE, category="laws",
    )
    bridge.enqueue_catalog(catalog)
    candidate_key = queue.list_items(state="queued")[0]["candidate_key"]
    assert queue.mark_result(candidate_key, success=False, error="fixture network failure", retry_delay_seconds=30) is True
    restarted_queue = DownloadQueue(tmp_path / "download_queue.json", allowed_hosts={"rc.majlis.ir"})
    due = restarted_queue.due_retries(now=datetime.now(timezone.utc) + timedelta(seconds=31))
    assert len(due) == 1
    assert due[0]["attempt_count"] == 1
    assert restarted_queue.mark_result(candidate_key, success=False, error="second failure") is True
    assert restarted_queue.mark_result(candidate_key, success=False, error="third failure") is True
    assert restarted_queue.list_items(state="failed")[0]["attempt_count"] == 3
    assert restarted_queue.due_retries(now=datetime.now(timezone.utc) + timedelta(days=1)) == []
