from legal_bot.ingestion.connectors import DoticRegulationsConnector, OfficialGazetteConnector, JudiciaryPortalConnector


def test_dotic_parses_only_allowed_host_and_pdf():
    c = DoticRegulationsConnector()
    html = '<a href="/files/law.pdf">قانون نمونه ۱۴۰۲</a><a href="https://evil.example/x.pdf">خارجی</a>'
    found = list(c.discover_from_html(html, "https://dotic.ir/", category="laws"))
    assert len(found) == 1 and found[0].asset_url == "https://dotic.ir/files/law.pdf"
    assert found[0].source_role.endswith("unverified")


def test_dotic_rejects_wrong_category_and_host():
    c = DoticRegulationsConnector()
    html = '<a href="/files/law.pdf">قانون</a>'
    assert list(c.discover_from_html(html, "https://dotic.ir/", category="judiciary_advisory_opinions")) == []
    assert list(c.discover_from_html(html, "https://fake-dotic.ir/", category="laws")) == []


def test_gazette_discovers_candidate_without_claiming_validity():
    c = OfficialGazetteConnector()
    found = list(c.discover_from_html('<a href="/pdf/notice.pdf">آگهی قانون ۱۴۰۱</a>',
                                      "https://rrk.ir/", category="official_publications"))
    assert len(found) == 1
    assert "اعتبار حقوقی" in found[0].notes
    assert found[0].asset_url.endswith("notice.pdf")


def test_judiciary_portal_supports_three_judicial_families():
    c = JudiciaryPortalConnector()
    html = '<a href="/docs/opinion.pdf">نظریه مشورتی ۱۴۰۳</a>'
    for category in ("supreme_court_unity_rulings", "administrative_justice_general_assembly_rulings",
                     "judiciary_advisory_opinions"):
        assert len(list(c.discover_from_html(html, "https://eadil.com/", category=category))) == 1


def test_judiciary_portal_rejects_unrelated_and_external_links():
    c = JudiciaryPortalConnector()
    html = '<a href="https://evil.example/ruling.pdf">رأی</a>'
    assert list(c.discover_from_html(html, "https://eadil.com/", category="supreme_court_unity_rulings")) == []


def test_adapters_are_fixture_only_and_do_not_promote_authority():
    for c in (DoticRegulationsConnector(), OfficialGazetteConnector(), JudiciaryPortalConnector()):
        assert "unverified" in c.definition.source_role
        assert c.definition.base_url.startswith("https://")
