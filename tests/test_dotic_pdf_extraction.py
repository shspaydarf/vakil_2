import hashlib
import json
from pathlib import Path

import fitz
import pytest

from legal_bot.ingestion.dotic_pdf_extraction import (
    DoticExtractionError, run_extraction,
)


def make_pdf(path: Path, pages: int = 23) -> str:
    doc = fitz.open()
    for number in range(1, pages + 1):
        page = doc.new_page()
        page.insert_text((72, 72), f"Synthetic Persian legal document page {number}. Enough text for extraction.")
    doc.save(path)
    doc.close()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_manifest(path: Path, pdf: Path, digest: str) -> Path:
    manifest = {
        "phase": "10.4.6", "stored_original": str(pdf), "sha256": digest,
        "source_url": "https://dotic.ir/files/synthetic.pdf",
        "technical_validation": "passed", "legal_authenticity_verified": False,
        "active_bank_write": False,
    }
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_extraction_processes_only_twenty_pages_then_resumes(tmp_path):
    pdf = tmp_path / "source.pdf"
    digest = make_pdf(pdf, 23)
    manifest = make_manifest(tmp_path / "manifest.json", pdf, digest)
    first = run_extraction(manifest, run_ocr=False)
    assert first["pages_extracted_so_far"] == 20
    assert first["complete"] is False
    assert first["next_page"] == 21
    second = run_extraction(manifest, run_ocr=False)
    assert second["pages_extracted_so_far"] == 23
    assert second["complete"] is True
    assert [p["page_number"] for p in second["pages"]] == list(range(1, 24))


def test_rejects_manifest_hash_mismatch(tmp_path):
    pdf = tmp_path / "source.pdf"
    digest = make_pdf(pdf, 1)
    manifest = make_manifest(tmp_path / "manifest.json", pdf, digest)
    pdf.write_bytes(pdf.read_bytes() + b"tamper")
    with pytest.raises(DoticExtractionError, match="هش PDF"):
        run_extraction(manifest)


def test_rejects_manifest_that_claims_legal_authenticity(tmp_path):
    pdf = tmp_path / "source.pdf"
    digest = make_pdf(pdf, 1)
    manifest = make_manifest(tmp_path / "manifest.json", pdf, digest)
    data = json.loads(manifest.read_text())
    data["legal_authenticity_verified"] = True
    manifest.write_text(json.dumps(data))
    with pytest.raises(DoticExtractionError, match="وضعیت ایمنی"):
        run_extraction(manifest)


def test_page_budget_is_hard_limited_to_twenty(tmp_path):
    pdf = tmp_path / "source.pdf"
    digest = make_pdf(pdf, 1)
    manifest = make_manifest(tmp_path / "manifest.json", pdf, digest)
    with pytest.raises(DoticExtractionError, match="بودجه"):
        run_extraction(manifest, max_pages=21)


def test_extraction_writes_sidecar_only_and_never_active_bank(tmp_path):
    pdf = tmp_path / "source.pdf"
    digest = make_pdf(pdf, 2)
    manifest = make_manifest(tmp_path / "manifest.json", pdf, digest)
    active_bank = tmp_path / "laws.json"
    original = b'{"documents": []}\n'
    active_bank.write_bytes(original)
    result = run_extraction(manifest, run_ocr=False)
    assert result["complete"] is True
    assert result["active_bank_write"] is False
    assert Path(result["output_path"]).exists()
    assert active_bank.read_bytes() == original
