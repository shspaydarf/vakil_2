import hashlib
from legal_bot.ingestion.discovery_memory_bridge import DiscoveryMemoryBridge
from legal_bot.ingestion.document_catalog import DocumentCatalog
from legal_bot.ingestion.source_registry import SourceRecord, SourceRegistry


def _source(status="verified", authority="official_primary", access="polite_public_read"):
    verification = ({"reviewer_id":"test", "reviewed_at":"2026-11-01", "evidence_ref":"local:test",
                     "evidence_sha256":hashlib.sha256(b"evidence").hexdigest()} if status == "verified" else {})
    return SourceRecord(source_id="official", display_name="Official", publisher="Issuer", jurisdiction="IR",
                        authority_level=authority, document_types=("law",), allowed_hosts=("laws.example.ir",),
                        canonical_roots=("https://laws.example.ir/",), access_mode=access, status=status,
                        verification=verification)


def _record(source_id="official", external="L-1"):
    return {"source_id":source_id, "document_type":"law", "title":"قانون نمونه",
            "external_id":external, "document_url":"https://laws.example.ir/law/1",
            "document_number":"۱۲۳", "approval_date":"۱۴۰۰-۰۱-۰۱", "issuer":"مجلس شورای اسلامی"}


def _bridge(tmp_path, source=None):
    registry = SourceRegistry(tmp_path/"registry.json")
    registry.upsert(source or _source(), actor_id="test", reason="fixture")
    catalog = DocumentCatalog(tmp_path/"catalog.json", source_registry=registry)
    return DiscoveryMemoryBridge(registry=registry, catalog=catalog, checkpoint_path=tmp_path/"checkpoints.json"), catalog


def test_discovery_batch_catalogs_and_advances_cursor_after_commit(tmp_path):
    bridge, catalog = _bridge(tmp_path)
    result = bridge.ingest_discovery_batch("official", [_record()], next_cursor="page-2")
    assert result["added"] == 1 and bridge.get_cursor("official") == "page-2"
    assert len(catalog.list_documents()) == 1


def test_same_batch_retry_does_not_duplicate_catalog_record(tmp_path):
    bridge, _ = _bridge(tmp_path)
    bridge.ingest_discovery_batch("official", [_record()], next_cursor="page-2")
    result = bridge.ingest_discovery_batch("official", [_record()], next_cursor="page-2")
    assert result["duplicates_skipped"] == 1 and result["total_documents"] == 1


def test_only_verified_official_primary_records_become_pipeline_candidates(tmp_path):
    bridge, _ = _bridge(tmp_path)
    bridge.ingest_discovery_batch("official", [_record()])
    candidates = bridge.pipeline_candidates()
    assert len(candidates) == 1 and candidates[0]["document_kind"] == "law"
    assert candidates[0]["document_id"].startswith("machina_doc_")


def test_secondary_source_is_cataloged_but_never_pipeline_authority(tmp_path):
    secondary = _source(authority="secondary")
    # Secondary source may be verified as a source, but cannot become official_primary.
    bridge, _ = _bridge(tmp_path, secondary)
    row = _record()
    row["source_id"] = "official"
    bridge.ingest_discovery_batch("official", [row])
    assert bridge.pipeline_candidates() == []


def test_unregistered_source_and_mismatched_source_are_rejected(tmp_path):
    bridge, _ = _bridge(tmp_path)
    try:
        bridge.ingest_discovery_batch("unknown", [_record("unknown")])
        assert False
    except ValueError as exc:
        assert str(exc) == "source_not_registered"
    try:
        bridge.ingest_discovery_batch("official", [_record("other")])
        assert False
    except ValueError as exc:
        assert str(exc) == "discovery_record_source_mismatch"


def test_disabled_network_policy_is_reported_without_network_attempt(tmp_path):
    bridge, _ = _bridge(tmp_path, _source(access="disabled"))
    policy = bridge.source_policy("official")
    assert policy["network_permitted"] is False
    assert bridge.status_report()["network_calls_performed"] is False
