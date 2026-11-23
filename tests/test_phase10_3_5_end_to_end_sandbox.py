"""Phase 10.3.5: local-PDF end-to-end drill with an isolated sandbox bank.

This is deliberately synthetic: it validates the complete software handoff
without claiming an official source download or legal-status determination.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import fitz

from legal_bot.ingestion.maintenance_runner import run_maintenance_cycle
from legal_bot.ingestion.pdf_text_extractor import ExtractionPolicy, extract_pdf_text


def _make_local_pdf(path: Path) -> str:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "SYNTHETIC LEGAL DOCUMENT FOR PIPELINE TEST", fontsize=12)
    page.insert_text((72, 100), "This fixture is not an official Iranian legal document.", fontsize=10)
    doc.save(path)
    doc.close()
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _candidate():
    return {
        "source_id": "synthetic_fixture",
        "document_kind": "law",
        "issuer": "TEST ISSUER",
        "official_number": "SYN-001",
        "approval_date": "1405-01-01",
        "title": "سند حقوقی آزمایشی ـ فاقد اعتبار رسمی",
        "external_id": "synthetic-001",
        "source_url": "https://fixture.invalid/doc/synthetic-001",
    }


def test_full_local_pdf_to_isolated_sandbox_bank(tmp_path):
    pdf = tmp_path / "fixture.pdf"
    digest = _make_local_pdf(pdf)
    candidate = _candidate()
    sandbox_bank = tmp_path / "sandbox_bank.json"
    sandbox_bank.write_text(json.dumps({"documents": []}), encoding="utf-8")

    def discover():
        return [dict(candidate)]

    def acquire(row):
        assert row["source_id"] == "synthetic_fixture"
        return {"local_path": str(pdf), "page_count": 1, "source_pdf_sha256": digest}

    def extract(row):
        result = extract_pdf_text(
            row["local_path"],
            policy=ExtractionPolicy(min_chars_per_page=10, min_text_page_ratio=1.0),
            expected_sha256=digest,
        )
        text = "\n".join(page["text"] for page in result.pages)
        return {
            "text": text,
            "content_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "page_count": result.page_count,
            "extraction_quality": result.quality,
            "source_pdf_sha256": result.source_sha256,
        }

    def validate(row):
        # Synthetic fixture-only screening; never evidence of official status.
        okay = "SYNTHETIC LEGAL DOCUMENT" in row["text"]
        return {
            "accepted": okay,
            "primary_source_verified": okay,
            "reason": None if okay else "fixture_text_missing",
            "validation_scope": "synthetic_test_only_not_legal_evidence",
        }

    def sandbox_import(row):
        bank = json.loads(sandbox_bank.read_text(encoding="utf-8"))
        bank["documents"].append({
            "document_id": row["document_id"],
            "title": row["title"],
            "content_sha256": row["content_sha256"],
            "text": row["text"],
            "test_only": True,
        })
        sandbox_bank.write_text(json.dumps(bank, ensure_ascii=False), encoding="utf-8")
        return {"imported": True, "target": "isolated_sandbox_only"}

    result = run_maintenance_cycle(
        discover=discover,
        acquire=acquire,
        extract=extract,
        validate=validate,
        state_path=tmp_path / "state.json",
        report_path=tmp_path / "run_report.json",
        import_document=sandbox_import,
        allow_bank_import=True,
    )

    assert result["discovery_succeeded"] is True
    assert result["cycle"]["processed"] == 1
    assert result["cycle"]["imported"] == 1
    assert result["bank_import_callback_executed"] is True
    assert result["active_bank_changed"] is None  # callback target is not inferred
    assert result["active_bank_change_verified"] is False
    bank = json.loads(sandbox_bank.read_text(encoding="utf-8"))
    assert len(bank["documents"]) == 1
    assert bank["documents"][0]["test_only"] is True
    report = json.loads((tmp_path / "run_report.json").read_text(encoding="utf-8"))
    assert report["legal_validity_proven"] is False
    assert report["live_source_connectivity_proven"] is False


def test_validation_rejection_quarantines_without_import(tmp_path):
    pdf = tmp_path / "fixture.pdf"
    _make_local_pdf(pdf)
    imports = []

    def acquire(row):
        return {"local_path": str(pdf), "page_count": 1}

    def extract(row):
        text = "synthetic text"
        return {"text": text, "content_sha256": hashlib.sha256(text.encode()).hexdigest()}

    result = run_maintenance_cycle(
        discover=lambda: [_candidate()], acquire=acquire, extract=extract,
        validate=lambda row: {"accepted": False, "primary_source_verified": False, "reason": "not_official"},
        state_path=tmp_path / "state.json", report_path=tmp_path / "report.json",
        import_document=lambda row: imports.append(row) or {"imported": True},
        allow_bank_import=True,
    )
    assert result["cycle"]["quarantined"] == 1
    assert result["cycle"]["imported"] == 0
    assert imports == []


def test_same_version_is_skipped_when_catalog_supplies_known_hash(tmp_path):
    pdf = tmp_path / "fixture.pdf"
    _make_local_pdf(pdf)
    text = "known catalog text"
    digest = hashlib.sha256(text.encode()).hexdigest()
    candidate = _candidate() | {"content_sha256": digest}
    calls = {"acquire": 0}

    def acquire(row):
        calls["acquire"] += 1
        return {"page_count": 1}

    def extract(row):
        return {"content_sha256": digest, "text": text}

    def validate(row):
        return {"accepted": True, "primary_source_verified": True}

    for _ in range(2):
        result = run_maintenance_cycle(
            discover=lambda: [candidate], acquire=acquire, extract=extract,
            validate=validate, state_path=tmp_path / "state.json",
            report_path=tmp_path / "report.json",
        )
    assert result["cycle"]["duplicates"] == 1
    assert calls["acquire"] == 1


def test_run_report_and_active_bank_are_untouched_in_default_mode(tmp_path):
    pdf = tmp_path / "fixture.pdf"
    _make_local_pdf(pdf)
    active_bank = tmp_path / "active_bank.json"
    original = b'{"documents": []}\n'
    active_bank.write_bytes(original)
    text = "screened text"
    result = run_maintenance_cycle(
        discover=lambda: [_candidate()],
        acquire=lambda row: {"page_count": 1, "local_path": str(pdf)},
        extract=lambda row: {"text": text, "content_sha256": hashlib.sha256(text.encode()).hexdigest()},
        validate=lambda row: {"accepted": True, "primary_source_verified": True},
        state_path=tmp_path / "state.json", report_path=tmp_path / "report.json",
    )
    assert result["cycle"]["processed"] == 1
    assert result["cycle"]["imported"] == 0
    assert active_bank.read_bytes() == original
