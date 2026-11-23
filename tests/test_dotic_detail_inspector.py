import pytest
from legal_bot.ingestion.dotic_detail_inspector import inspect_html

PAGE = "https://dotic.ir/news/21843"

def test_extracts_same_host_https_pdf_as_unverified_candidate():
    html = '<a href="/files/ruling.pdf">متن کامل رأی شماره 1709520</a>'
    report = inspect_html(html, PAGE)
    assert len(report["pdf_candidates"]) == 1
    assert report["pdf_candidates"][0]["url"] == "https://dotic.ir/files/ruling.pdf"
    assert report["pdf_candidates"][0]["official_document_confirmed"] is False
    assert report["limits"]["pdf_downloads"] == 0

def test_rejects_external_and_http_links():
    html = '<a href="https://evil.example/a.pdf">x</a><a href="http://dotic.ir/b.pdf">y</a>'
    report = inspect_html(html, PAGE)
    assert report["pdf_candidates"] == []
    assert len(report["rejected_links"]) == 2

def test_deduplicates_pdf_and_ignores_non_pdf():
    html = '<a href="/a.pdf">A</a><a href="/a.pdf">A again</a><a href="/page">page</a>'
    assert len(inspect_html(html, PAGE)["pdf_candidates"]) == 1

def test_rejects_untrusted_page_url():
    with pytest.raises(ValueError):
        inspect_html('<a href="/a.pdf">A</a>', "http://dotic.ir/news/1")

def test_extracts_metadata_hints_without_asserting_identity():
    report = inspect_html('<p>شماره: 1709520 تاریخ 1405/07/12</p>', PAGE)
    assert report["metadata_hints"]["document_number_candidates"] == ["1709520"]
    assert report["metadata_hints"]["date_candidates"] == ["1405/07/12"]
    assert report["limits"]["legal_authenticity_verified"] is False
