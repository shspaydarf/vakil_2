import json
from pathlib import Path

import pytest

from legal_bot.ingestion.official_source_matcher import (
    match_document_against_sources, write_source_match_report,
)

DOC = {
    "document_id": "law-1",
    "metadata": {"title": "قانون نمونه", "document_type": "قانون", "issuer": "مجلس شورای اسلامی", "number": "۱۲۳", "approval_date": "۱۴۰۰/۰۱/۰۱"},
    "normalized_text": "ماده ۱ - متن آزمایشی قانون\nماده ۲ - متن دوم",
}


def test_exact_official_record_is_candidate_not_proof():
    catalog = {"sources": [{"source_id": "majles_rc", "source_role": "preferred_parliamentary_discovery"}]}
    source = {"source_id": "majles_rc", "page_url": "https://rc.majlis.ir/law/1", "metadata": DOC["metadata"], "normalized_text": DOC["normalized_text"]}
    report = match_document_against_sources(DOC, [source], source_catalog=catalog)
    assert report.status == "official_source_match_candidate"
    assert report.source_comparisons[0]["text_comparison"] == "exact_match"
    assert report.official_confirmation is False
    assert report.live_source_access_performed is False
    assert report.legal_validity_proven is False


def test_secondary_source_never_becomes_official_confirmation():
    source = {"source_id": "ekhtebar", "source_role": "secondary_discovery", "page_url": "https://www.ekhtebar.ir/x", "metadata": DOC["metadata"], "text": DOC["normalized_text"]}
    report = match_document_against_sources(DOC, [source])
    assert report.status == "source_comparison_inconclusive"
    assert any(x["code"] == "secondary_source_match_only" for x in report.findings)
    assert report.official_confirmation is False


def test_metadata_conflict_and_text_difference_are_flagged():
    source = {"source_id": "official_primary", "source_role": "official_primary", "metadata": {"title": "قانون نمونه دیگر", "issuer": "مرجع دیگر"}, "text": "متن کاملاً متفاوت"}
    report = match_document_against_sources(DOC, [source])
    codes = {x["code"] for x in report.findings}
    assert "source_metadata_conflict" in codes
    assert "source_text_difference" in codes


def test_no_source_records_is_explicit():
    report = match_document_against_sources(DOC, [])
    assert report.status == "no_source_records_provided"
    assert report.source_comparisons == []


def test_invalid_thresholds_rejected():
    with pytest.raises(ValueError):
        match_document_against_sources(DOC, [], exact_text_threshold=0.8, close_text_threshold=0.9)


def test_report_written_atomically(tmp_path):
    report = match_document_against_sources(DOC, [])
    target = write_source_match_report(report, tmp_path / "07_source_match_report.json")
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["validator_version"] == "4.5.0"
    assert payload["active_bank_changed"] is False
