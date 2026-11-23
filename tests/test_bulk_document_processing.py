import hashlib
import json
from pathlib import Path

import fitz
import pytest

from legal_bot.ingestion.bulk_document_processing import (
    BulkPDFItem, BulkProcessingError, BulkProcessingPolicy, process_bulk_pdfs,
)


def make_pdf(path: Path, pages: int = 1) -> Path:
    doc = fitz.open()
    for n in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), ("قانون آزمایشی ماده یک " * 8) + f" صفحه {n+1}")
    doc.save(path)
    doc.close()
    return path


def item(path: Path, **kwargs) -> BulkPDFItem:
    base = dict(document_id="doc-1", source_id="majlis", source_class="official_primary",
                source_verified=True, acquisition_status="downloaded", pdf_path=str(path),
                expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), document_type="law")
    base.update(kwargs)
    return BulkPDFItem(**base)


def test_processes_explicit_local_pdf_and_writes_review_report(tmp_path):
    pdf = make_pdf(tmp_path / "a.pdf")
    out = tmp_path / "out"
    report = process_bulk_pdfs([item(pdf)], out)
    assert report["completed_documents"] == 1
    assert report["active_bank_modified"] is False
    assert report["results"][0]["status"] == "completed_review_required"
    assert (out / "doc-1" / "05_staging_document.json").is_file()
    assert json.loads((out / "bulk_processing_report.json").read_text())["review_required"] is True


def test_rejects_unverified_source(tmp_path):
    pdf = make_pdf(tmp_path / "a.pdf")
    with pytest.raises(BulkProcessingError, match="تأیید انسانی"):
        process_bulk_pdfs([item(pdf, source_verified=False)], tmp_path / "out")


def test_rejects_secondary_by_default(tmp_path):
    pdf = make_pdf(tmp_path / "a.pdf")
    with pytest.raises(BulkProcessingError, match="مجاز نیست"):
        process_bulk_pdfs([item(pdf, source_class="secondary")], tmp_path / "out")


def test_secondary_requires_explicit_policy_opt_in(tmp_path):
    pdf = make_pdf(tmp_path / "a.pdf")
    report = process_bulk_pdfs([item(pdf, source_class="secondary")], tmp_path / "out",
                               policy=BulkProcessingPolicy(allow_secondary_sources=True))
    assert report["completed_documents"] == 1


def test_rejects_hash_mismatch(tmp_path):
    pdf = make_pdf(tmp_path / "a.pdf")
    with pytest.raises(BulkProcessingError, match="هش فایل"):
        process_bulk_pdfs([item(pdf, expected_sha256="0" * 64)], tmp_path / "out")


def test_rejects_duplicate_document_ids(tmp_path):
    pdf = make_pdf(tmp_path / "a.pdf")
    with pytest.raises(BulkProcessingError, match="تکراری"):
        process_bulk_pdfs([item(pdf), item(pdf, source_id="another")], tmp_path / "out")


def test_enforces_document_and_source_budgets(tmp_path):
    pdf = make_pdf(tmp_path / "a.pdf")
    policy = BulkProcessingPolicy(max_documents=2, max_documents_per_source=1)
    with pytest.raises(BulkProcessingError, match="سقف تعداد اسناد برای یک منبع"):
        process_bulk_pdfs([item(pdf, document_id="a"), item(pdf, document_id="b")], tmp_path / "out", policy=policy)


def test_rejects_non_pdf_and_non_downloaded(tmp_path):
    txt = tmp_path / "a.txt"
    txt.write_text("not pdf")
    with pytest.raises(BulkProcessingError, match="downloaded"):
        process_bulk_pdfs([item(txt, acquisition_status="queued")], tmp_path / "out")


def test_enforces_page_budget_before_pipeline(tmp_path):
    pdf = make_pdf(tmp_path / "a.pdf", pages=3)
    report = process_bulk_pdfs([item(pdf)], tmp_path / "out", policy=BulkProcessingPolicy(max_total_pages=2))
    assert report["failed_documents"] == 1
    assert "مجموع صفحات" in report["results"][0]["error"]


def test_item_failure_isolated_and_recorded(tmp_path, monkeypatch):
    pdf = make_pdf(tmp_path / "a.pdf")
    import legal_bot.ingestion.bulk_document_processing as module
    def fail(*args, **kwargs):
        raise RuntimeError("fixture failure")
    monkeypatch.setattr(module, "process_pdf_document", fail)
    report = process_bulk_pdfs([item(pdf)], tmp_path / "out")
    assert report["failed_documents"] == 1
    assert report["results"][0]["error_type"] == "RuntimeError"


def test_empty_batch_and_invalid_policy_rejected(tmp_path):
    with pytest.raises(BulkProcessingError, match="خالی"):
        process_bulk_pdfs([], tmp_path / "out")
    pdf = make_pdf(tmp_path / "a.pdf")
    with pytest.raises(BulkProcessingError, match="مثبت"):
        process_bulk_pdfs([item(pdf)], tmp_path / "out", policy=BulkProcessingPolicy(max_documents=0))
