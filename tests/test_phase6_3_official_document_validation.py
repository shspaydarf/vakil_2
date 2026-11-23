import hashlib
import json
from pathlib import Path

from legal_bot.ingestion.official_document_validation import validate_official_pdf_evidence

CANDIDATE = "MACHINA-PHASE6-1-IR-LAW-001"
TITLE = "قانون احکام دائمی برنامه های توسعه کشور"


def manifest(path=None, sha=None):
    return {
        "candidate_id": CANDIDATE,
        "document_title": TITLE,
        "acquisition_status": "downloaded_pending_integrity_review",
        "mirror_fallback_used": False,
        "final_source_url": "https://rc.majlis.ir/files/official-law.pdf",
        "original_pdf": str(path) if path else None,
        "sha256": sha,
    }


def test_current_phase62_blocked_manifest_stays_blocked_and_reported(tmp_path):
    path = Path(__file__).resolve().parents[1] / "legal_bot/data/iran/ingestion/test_candidates/phase6_2_acquisition_manifest.json"
    acquisition = json.loads(path.read_text(encoding="utf-8"))
    report = validate_official_pdf_evidence(acquisition, output_path=tmp_path / "report.json")
    assert report["validation_status"] == "blocked_pending_official_pdf"
    assert "official_pdf_not_acquired" in report["reason_codes"]
    assert report["legal_authenticity_confirmed"] is False
    assert json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))["active_bank_modified"] is False


def test_valid_technical_fixture_passes_but_not_legal_authenticity(tmp_path):
    pdf = tmp_path / "fixture.pdf"
    # Minimal one-page PDF generated with PyMuPDF for structural validation.
    import fitz
    doc = fitz.open()
    doc.new_page()
    doc.save(pdf)
    doc.close()
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    result = validate_official_pdf_evidence(manifest(pdf, digest))
    assert result["technical_integrity_passed"] is True
    assert result["validation_status"] == "technical_integrity_passed_pending_human_legal_review"
    assert result["legal_authenticity_confirmed"] is False


def test_hash_mismatch_fails_closed(tmp_path):
    pdf = tmp_path / "fixture.pdf"
    pdf.write_bytes(b"%PDF-1.4\nnot-a-real-pdf")
    result = validate_official_pdf_evidence(manifest(pdf, "0" * 64))
    assert result["technical_integrity_passed"] is False
    assert "sha256_mismatch" in result["reason_codes"]
    assert "pdf_structure_invalid" in result["reason_codes"]


def test_non_official_host_is_rejected(tmp_path):
    pdf = tmp_path / "fixture.pdf"
    import fitz
    doc = fitz.open(); doc.new_page(); doc.save(pdf); doc.close()
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    item = manifest(pdf, digest)
    item["final_source_url"] = "https://faolex.fao.org/docs/pdf/ira224883.pdf"
    result = validate_official_pdf_evidence(item)
    assert "official_pdf_source_endpoint_unverified" in result["reason_codes"]
    assert result["technical_integrity_passed"] is False


def test_missing_file_is_rejected(tmp_path):
    result = validate_official_pdf_evidence(manifest(tmp_path / "missing.pdf", "a" * 64))
    assert "original_pdf_missing" in result["reason_codes"]
    assert result["technical_integrity_passed"] is False
