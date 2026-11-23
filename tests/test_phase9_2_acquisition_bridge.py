from pathlib import Path
from types import SimpleNamespace

from legal_bot.ingestion.phase9_2_acquisition_bridge import acquire_one_pdf_to_quarantine


class FakeDownloader:
    def __init__(self, storage_dir, outcome=None):
        self.storage_dir = Path(storage_dir)
        self.outcome = outcome or SimpleNamespace(
            path=str(self.storage_dir / "abc.pdf"), sha256="a" * 64,
            size_bytes=123, page_count=2, source_url="https://www.ekhtebar.ir/a.pdf",
            downloaded_at="2026-11-01T00:00:00+00:00", content_type="application/pdf")
        self.outcome.to_dict = lambda: {k: getattr(self.outcome, k) for k in (
            "path", "sha256", "size_bytes", "page_count", "source_url", "downloaded_at", "content_type")}
        self.calls = 0

    def download(self, url):
        self.calls += 1
        return self.outcome


def test_no_direct_pdf_does_not_call_downloader(tmp_path):
    q = tmp_path / "phase9_2_quarantine"
    d = FakeDownloader(q)
    result = acquire_one_pdf_to_quarantine(source_id="ekhtebar", source_url="https://www.ekhtebar.ir/laws/",
        staging_root=tmp_path, direct_pdf_observed=False, downloader=d)
    assert result["status"] == "blocked"
    assert result["reason"] == "direct_pdf_asset_not_independently_observed"
    assert d.calls == 0
    assert result["active_bank_modified"] is False


def test_ekhtebar_pdf_is_quarantine_only(tmp_path):
    d = FakeDownloader(tmp_path / "phase9_2_quarantine")
    result = acquire_one_pdf_to_quarantine(source_id="ekhtebar", source_url="https://www.ekhtebar.ir/a.pdf",
        staging_root=tmp_path, direct_pdf_observed=True, downloader=d)
    assert result["status"] == "secondary_downloaded_quarantine_only"
    assert result["source_role"] == "secondary_reference_only"
    assert result["human_review_required"] is True
    assert result["active_bank_modified"] is False
    assert d.calls == 1


def test_official_pdf_waits_for_human_review(tmp_path):
    d = FakeDownloader(tmp_path / "phase9_2_quarantine")
    result = acquire_one_pdf_to_quarantine(source_id="majles_rc", source_url="https://rc.majlis.ir/files/a.pdf",
        staging_root=tmp_path, direct_pdf_observed=True, downloader=d)
    assert result["status"] == "downloaded_pending_human_review"
    assert result["active_bank_modified"] is False


def test_wrong_storage_directory_blocks_download(tmp_path):
    d = FakeDownloader(tmp_path / "elsewhere")
    result = acquire_one_pdf_to_quarantine(source_id="ekhtebar", source_url="https://www.ekhtebar.ir/a.pdf",
        staging_root=tmp_path, direct_pdf_observed=True, downloader=d)
    assert result["reason"] == "downloader_storage_must_be_isolated_quarantine"
    assert d.calls == 0


def test_unallowlisted_source_rejected(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        acquire_one_pdf_to_quarantine(source_id="other", source_url="https://evil.example/a.pdf",
            staging_root=tmp_path, direct_pdf_observed=True, downloader=None)


def test_manifest_written_outside_active_bank(tmp_path):
    d = FakeDownloader(tmp_path / "phase9_2_quarantine")
    result = acquire_one_pdf_to_quarantine(source_id="ekhtebar", source_url="https://www.ekhtebar.ir/a.pdf",
        staging_root=tmp_path, direct_pdf_observed=True, downloader=d)
    assert Path(result["manifest_path"]).exists()
    assert "phase9_2_quarantine" in result["manifest_path"]
