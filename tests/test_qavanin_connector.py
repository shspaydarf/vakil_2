from pathlib import Path

import pytest

from legal_bot.ingestion.connectors import QavaninConnector

FIXTURE = Path(__file__).parent / "fixtures" / "ingestion" / "qavanin_search_results_sample.html"


def test_qavanin_parses_search_rows_as_unverified_candidates():
    connector = QavaninConnector()
    html = FIXTURE.read_text(encoding="utf-8")
    found = list(connector.discover_from_html(html, "https://qavanin.ir/", category="laws"))
    assert len(found) == 2
    assert found[0].source_id == "qavanin_national"
    assert found[0].source_record_id == "301745"
    assert found[0].title == "آیین‌نامه حمایت از تولید، دانش‌بنیان و اشتغال‌آفرین"
    assert found[0].document_date == "1401/12/21"
    assert found[0].issuer == "هیئت وزیران"
    assert found[0].page_url == "https://qavanin.ir/Law/TreeText/?IDS=301745"
    assert found[0].source_role.endswith("unverified")
    assert "ورود به بانک فعال مجاز نیست" in found[0].notes


def test_qavanin_preserves_long_document_ids_as_strings():
    html = FIXTURE.read_text(encoding="utf-8")
    found = list(QavaninConnector().discover_from_html(html, "https://qavanin.ir/", category="laws"))
    assert found[1].source_record_id == "98765432101234567890"
    assert "IDS=98765432101234567890" in found[1].page_url


def test_qavanin_rejects_external_hosts_and_wrong_categories():
    connector = QavaninConnector()
    html = FIXTURE.read_text(encoding="utf-8")
    assert list(connector.discover_from_html(html, "https://evil.example/", category="laws")) == []
    assert list(connector.discover_from_html(html, "http://qavanin.ir/", category="laws")) == []
    assert list(connector.discover_from_html(html, "https://qavanin.ir/", category="random")) == []


def test_qavanin_does_not_parse_browser_challenges_as_documents():
    challenge = '<html>__arcsjs checking your browser <script>captcha</script></html>'
    assert list(QavaninConnector().discover_from_html(challenge, "https://qavanin.ir/", category="laws")) == []


def test_qavanin_builds_bounded_read_only_search_url():
    url = QavaninConnector.build_search_url("قانون مدنی", page=2, in_text=True, limit=40)
    assert url.startswith("https://qavanin.ir/?")
    assert "IsTextSearch=true" in url
    assert "PageNumber=2" in url
    assert "size=50" in url
    with pytest.raises(ValueError):
        QavaninConnector.build_search_url("  ")
    with pytest.raises(ValueError):
        QavaninConnector.build_search_url("قانون", page=0)


def test_qavanin_document_url_rejects_invalid_ids():
    assert QavaninConnector.document_url("123456") == "https://qavanin.ir/Law/TreeText/?IDS=123456"
    with pytest.raises(ValueError):
        QavaninConnector.document_url("123abc")
