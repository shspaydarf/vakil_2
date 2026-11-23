import hashlib
from pathlib import Path

import fitz

from legal_bot.ingestion.integration_orchestrator import run_document_validation, process_queued_candidate
from legal_bot.ingestion.download_queue import DownloadQueue
from legal_bot.ingestion.models import CandidateDocument
from legal_bot.ingestion.secure_pdf_fetcher import DownloadedPDF


def _fixture_pdf(path: Path) -> str:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "قانون نمونه\nمجلس شورای اسلامی\nماده ۱ - متن آزمایشی قانون")
    doc.save(path)
    doc.close()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _inputs(pdf_path: Path):
    digest = _fixture_pdf(pdf_path)
    candidate = {
        "candidate_key": "fixture-law-001",
        "source_id": "majles_rc",
        "source_name": "مرکز پژوهش‌های مجلس",
        "source_role": "preferred_parliamentary_discovery",
        "document_type": "قانون",
        "title": "قانون نمونه",
        "issuer": "مجلس شورای اسلامی",
        "document_number": "۱۲۳",
        "page_url": "https://rc.majlis.ir/fa/law/print_version/123",
        "asset_url": "https://rc.majlis.ir/files/123.pdf",
    }
    download = {
        "path": str(pdf_path), "sha256": digest, "size_bytes": pdf_path.stat().st_size,
        "page_count": 1, "source_url": candidate["asset_url"],
        "downloaded_at": "2026-11-01T00:00:00+00:00", "content_type": "application/pdf",
    }
    pdf_doc = fitz.open(pdf_path)
    extracted_fixture_text = "\n".join(page.get_text("text") for page in pdf_doc)
    pdf_doc.close()
    source_records = [{
        "source_id": "majles_rc",
        "source_role": "preferred_parliamentary_discovery",
        "page_url": candidate["page_url"],
        "metadata": {
            "title": "قانون نمونه", "document_type": "قانون",
            "issuer": "مجلس شورای اسلامی", "number": "۱۲۳",
        },
        "text": extracted_fixture_text,
    }]
    return candidate, download, source_records


def test_full_local_pipeline_and_validation_bundle(tmp_path):
    pdf = tmp_path / "fixture.pdf"
    candidate, download, source_records = _inputs(pdf)
    result = run_document_validation(
        pdf, tmp_path / "out", candidate=candidate,
        download_manifest=download, source_records=source_records, run_ocr=False,
        human_decision={
            "approved": True, "reviewer_id": "qa-reviewer",
            "decided_at": "2026-11-01T01:00:00+03:30",
        },
    )
    assert result["final_status"] == "approved_for_phase5_review"
    assert result["phase5_eligible"] is True
    assert result["official_confirmation"] is False
    assert result["active_bank_changed"] is False
    assert result["import_performed"] is False
    for name in (
        "05_staging_document.json", "06_provenance_report.json",
        "07_metadata_report.json", "08_completeness_report.json",
        "09_version_conflict_report.json", "10_source_match_report.json",
        "11_final_validation_report.json", "12_integration_manifest.json",
    ):
        assert (tmp_path / "out" / name).is_file()


def test_bad_download_hash_fails_closed(tmp_path):
    pdf = tmp_path / "fixture.pdf"
    candidate, download, source_records = _inputs(pdf)
    download["sha256"] = "0" * 64
    result = run_document_validation(
        pdf, tmp_path / "out", candidate=candidate,
        download_manifest=download, source_records=source_records, run_ocr=False,
    )
    assert result["final_status"] == "blocked_pending_correction"
    assert result["phase5_eligible"] is False


def test_missing_source_records_cannot_pass_final_gate(tmp_path):
    pdf = tmp_path / "fixture.pdf"
    candidate, download, _ = _inputs(pdf)
    result = run_document_validation(
        pdf, tmp_path / "out", candidate=candidate,
        download_manifest=download, source_records=[], run_ocr=False,
    )
    assert result["final_status"] == "blocked_pending_correction"
    assert result["phase5_eligible"] is False


def test_queued_candidate_handoff_uses_downloader_and_updates_acquisition_state(tmp_path):
    pdf = tmp_path / "fixture.pdf"
    candidate_data, _, source_records = _inputs(pdf)
    candidate = CandidateDocument(
        source_id="majles_rc", source_name="مرکز پژوهش‌های مجلس",
        source_role="preferred_parliamentary_discovery",
        document_type="قانون", title="قانون نمونه",
        page_url=candidate_data["page_url"], asset_url=candidate_data["asset_url"],
        issuer="مجلس شورای اسلامی", document_number="۱۲۳",
    )
    queue = DownloadQueue(tmp_path / "queue.json", allowed_hosts={"rc.majlis.ir"})
    assert queue.enqueue([candidate])["added"] == 1

    class LocalDownloader:
        def download(self, url):
            assert url == candidate_data["asset_url"]
            return DownloadedPDF(
                path=str(pdf), sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),
                size_bytes=pdf.stat().st_size, page_count=1, source_url=url,
                downloaded_at="2026-11-01T00:00:00+00:00", content_type="application/pdf",
            )

    result = process_queued_candidate(
        queue, candidate.stable_key, LocalDownloader(), tmp_path / "queued-out",
        source_records=source_records, run_ocr=False,
    )
    assert result["active_bank_changed"] is False
    assert queue.list_items(state="downloaded")[0]["candidate_key"] == candidate.stable_key
