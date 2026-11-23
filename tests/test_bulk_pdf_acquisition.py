from dataclasses import dataclass
from pathlib import Path

import pytest

from legal_bot.ingestion.bulk_pdf_acquisition import BatchAcquisitionPolicy, BatchPDFAcquisition, acquisition_policy_summary
from legal_bot.ingestion.document_catalog import DocumentCatalog
from legal_bot.ingestion.source_registry import SourceRecord, SourceRegistry


def setup_catalog(tmp_path, *, authority="official_primary", status="verified"):
    reg = SourceRegistry(tmp_path / "sources.json")
    source = SourceRecord.from_dict({
        "source_id": "majles_rc", "display_name": "مجلس", "publisher": "مجلس شورای اسلامی", "jurisdiction": "IR",
        "authority_level": authority, "document_types": ["law"], "allowed_hosts": ["rc.majlis.ir"],
        "canonical_roots": ["https://rc.majlis.ir/fa/law"], "access_mode": "polite_public_read" if status == "verified" else "disabled",
        "status": status,
        "verification": {"reviewer_id": "human", "reviewed_at": "2026-11-01T10:00:00Z", "evidence_ref": "evidence", "evidence_sha256": "a" * 64} if status == "verified" else {},
    })
    reg.upsert(source, actor_id="admin", reason="review")
    cat = DocumentCatalog(tmp_path / "catalog.json", reg)
    result = cat.ingest([{"source_id": "majles_rc", "document_type": "law", "title": "قانون آزمایشی", "external_id": "law-1", "document_url": "https://rc.majlis.ir/fa/law/1"}], actor_id="admin", reason="inventory")
    doc_id = next(iter(cat.load()["documents"]))
    return reg, cat, doc_id


@dataclass
class FakePolicy:
    allow_downloads: bool = True
    max_asset_bytes: int = 5


@dataclass
class FakeResult:
    path: str = "/tmp/abc.pdf"
    sha256: str = "b" * 64
    size_bytes: int = 5
    page_count: int = 2
    source_url: str = "https://rc.majlis.ir/fa/law/1"
    downloaded_at: str = "2026-11-01T10:00:00+00:00"
    content_type: str = "application/pdf"
    def to_dict(self):
        return {"path": self.path, "sha256": self.sha256, "size_bytes": self.size_bytes, "page_count": self.page_count, "source_url": self.source_url, "downloaded_at": self.downloaded_at, "content_type": self.content_type}


class FakeDownloader:
    def __init__(self):
        self.policy = FakePolicy()
        self.calls = []
    def download(self, url):
        self.calls.append(url)
        return FakeResult()


def test_default_policy_is_dry_and_network_off(tmp_path):
    reg, cat, doc_id = setup_catalog(tmp_path)
    engine = BatchPDFAcquisition()
    plan = engine.plan(cat, reg, [doc_id])
    result = engine.execute(plan, catalog=cat, source_registry=reg, downloader=FakeDownloader(), state_path=tmp_path / "state.json", actor_id="admin")
    assert result["dry_run"] and result["attempted"] == 0
    assert not result["network_access_performed"]
    assert acquisition_policy_summary()["downloads_default_off"]


def test_only_verified_official_documents_are_planned(tmp_path):
    reg, cat, doc_id = setup_catalog(tmp_path, authority="secondary", status="verified")
    plan = BatchPDFAcquisition().plan(cat, reg, [doc_id])
    assert not plan["candidates"]
    assert plan["rejected"][0]["reason"] == "source_not_verified_official_primary"


def test_unknown_document_is_rejected(tmp_path):
    reg, cat, _ = setup_catalog(tmp_path)
    plan = BatchPDFAcquisition().plan(cat, reg, ["missing"])
    assert plan["rejected"][0]["reason"] == "document_not_in_catalog"


def test_unapproved_url_never_enters_plan(tmp_path):
    reg, cat, doc_id = setup_catalog(tmp_path)
    data = cat.load(); data["documents"][doc_id]["record"]["document_url"] = "https://evil.example/file.pdf"
    # Tampering is also caught by registry policy during planning.
    cat._atomic_write(data)
    plan = BatchPDFAcquisition().plan(cat, reg, [doc_id])
    assert not plan["candidates"]


def test_plan_is_deterministic_and_integrity_checked(tmp_path):
    reg, cat, doc_id = setup_catalog(tmp_path)
    engine = BatchPDFAcquisition()
    first = engine.plan(cat, reg, [doc_id]); second = engine.plan(cat, reg, [doc_id])
    assert first["plan_id"] == second["plan_id"]
    first["candidates"][0]["url"] = "https://evil.example/x"
    with pytest.raises(ValueError, match="integrity"):
        engine.execute(first, catalog=cat, source_registry=reg, downloader=FakeDownloader(), state_path=tmp_path / "state.json", actor_id="admin")


def test_live_execution_requires_both_explicit_opt_ins(tmp_path):
    reg, cat, doc_id = setup_catalog(tmp_path)
    plan = BatchPDFAcquisition().plan(cat, reg, [doc_id])
    engine = BatchPDFAcquisition(policy=BatchAcquisitionPolicy(allow_downloads=False))
    with pytest.raises(PermissionError, match="disabled by policy"):
        engine.execute(plan, catalog=cat, source_registry=reg, downloader=FakeDownloader(), state_path=tmp_path / "state.json", actor_id="admin", dry_run=False)


def test_successful_batch_records_hash_and_never_touches_active_bank(tmp_path):
    reg, cat, doc_id = setup_catalog(tmp_path)
    engine = BatchPDFAcquisition(policy=BatchAcquisitionPolicy(allow_downloads=True, max_total_bytes=10, max_total_pages=5))
    plan = engine.plan(cat, reg, [doc_id]); downloader = FakeDownloader()
    result = engine.execute(plan, catalog=cat, source_registry=reg, downloader=downloader, state_path=tmp_path / "state.json", actor_id="admin", dry_run=False)
    assert result["status"] == "completed" and len(result["acquired"]) == 1
    assert result["acquired"][0]["sha256"] == "b" * 64
    assert result["active_bank_write"] is False and len(downloader.calls) == 1


def test_per_source_and_document_budgets_are_enforced(tmp_path):
    reg, cat, doc_id = setup_catalog(tmp_path)
    engine = BatchPDFAcquisition(policy=BatchAcquisitionPolicy(max_documents=1, max_documents_per_source=1))
    plan = engine.plan(cat, reg, [doc_id, "not-real"])
    assert len(plan["candidates"]) == 1
    assert plan["rejected"]


def test_403_stops_batch_without_retry(tmp_path):
    reg, cat, doc_id = setup_catalog(tmp_path)
    class Blocked(FakeDownloader):
        def download(self, url):
            self.calls.append(url)
            raise ValueError("منبع دسترسی را محدود کرد: HTTP 403")
    engine = BatchPDFAcquisition(policy=BatchAcquisitionPolicy(allow_downloads=True, max_total_bytes=10, max_total_pages=5))
    plan = engine.plan(cat, reg, [doc_id]); downloader = Blocked()
    result = engine.execute(plan, catalog=cat, source_registry=reg, downloader=downloader, state_path=tmp_path / "state.json", actor_id="admin", dry_run=False)
    assert result["deferred"][0]["reason"] == "access_blocked_no_bypass"
    assert len(downloader.calls) == 1


def test_idempotent_rerun_does_not_download_twice(tmp_path):
    reg, cat, doc_id = setup_catalog(tmp_path)
    engine = BatchPDFAcquisition(policy=BatchAcquisitionPolicy(allow_downloads=True, max_total_bytes=10, max_total_pages=5))
    plan = engine.plan(cat, reg, [doc_id]); downloader = FakeDownloader(); state = tmp_path / "state.json"
    engine.execute(plan, catalog=cat, source_registry=reg, downloader=downloader, state_path=state, actor_id="admin", dry_run=False)
    again = engine.execute(plan, catalog=cat, source_registry=reg, downloader=downloader, state_path=state, actor_id="admin", dry_run=False)
    assert len(downloader.calls) == 1 and not again["acquired"]
