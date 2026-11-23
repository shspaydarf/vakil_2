import json
from pathlib import Path

from legal_bot.ingestion.official_pdf_acquisition import acquire_selected_official_pdf

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_PATH = ROOT / "legal_bot/data/iran/ingestion/test_candidates/phase6_1_candidate.json"


def candidate():
    return json.loads(CANDIDATE_PATH.read_text(encoding="utf-8"))


def test_missing_official_asset_url_fails_closed_and_writes_manifest(tmp_path):
    result = acquire_selected_official_pdf(candidate(), output_dir=tmp_path)
    assert result["acquisition_status"] == "blocked"
    assert result["reason_code"] == "official_pdf_asset_url_unresolved"
    assert result["sha256"] is None
    assert result["original_pdf"] is None
    assert Path(result["manifest_path"]).exists()


def test_mirror_url_is_rejected_without_downloader_call(tmp_path):
    class NeverCallDownloader:
        def download(self, url):
            raise AssertionError("downloader must not be called for a mirror")

    result = acquire_selected_official_pdf(
        candidate(), output_dir=tmp_path,
        asset_url="https://faolex.fao.org/docs/pdf/ira224883.pdf",
        downloader=NeverCallDownloader(),
    )
    assert result["acquisition_status"] == "blocked"
    assert result["reason_code"] == "asset_url_not_verified_official_pdf_endpoint"
    assert result["mirror_fallback_used"] is False


def test_official_html_page_is_not_misused_as_pdf_asset(tmp_path):
    result = acquire_selected_official_pdf(
        candidate(), output_dir=tmp_path,
        asset_url="https://rc.majlis.ir/fa/law/print_version/1014070",
    )
    assert result["reason_code"] == "asset_url_not_verified_official_pdf_endpoint"
    assert result["sha256"] is None


def test_download_error_is_recorded_without_claiming_acquisition(tmp_path):
    from legal_bot.ingestion.secure_pdf_fetcher import PDFDownloadError

    class RejectingDownloader:
        def download(self, url):
            raise PDFDownloadError("امکان بررسی DNS منبع وجود ندارد")

    result = acquire_selected_official_pdf(
        candidate(), output_dir=tmp_path,
        asset_url="https://rc.majlis.ir/files/official-law.pdf",
        downloader=RejectingDownloader(),
    )
    assert result["acquisition_status"] == "blocked"
    assert result["reason_code"] == "secure_downloader_rejected_source"
    assert result["sha256"] is None
    assert "DNS" in result["error"]


def test_candidate_identity_mismatch_is_rejected(tmp_path):
    item = candidate()
    item["candidate_id"] = "OTHER"
    result = acquire_selected_official_pdf(item, output_dir=tmp_path)
    assert result["reason_code"] == "candidate_identity_or_official_page_invalid"
