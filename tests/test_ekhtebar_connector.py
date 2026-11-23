import unittest
from pathlib import Path
from legal_bot.ingestion.connectors.ekhtebar import EkhtebarUnityRulingsConnector


class EkhtebarConnectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = Path(__file__).parent / "fixtures/ingestion/ekhtebar_unity_archive_sample.html"
        cls.html = fixture.read_text(encoding="utf-8")

    def test_discovers_pdf_and_zip_assets_only(self):
        connector = EkhtebarUnityRulingsConnector()
        items = list(connector.discover_from_html(
            self.html,
            "https://www.ekhtebar.ir/archive/unity-rulings/",
            category="supreme_court_unity_rulings",
        ))
        self.assertEqual(len(items), 3)
        self.assertTrue(all("ekhtebar.ir" in item.asset_url for item in items))
        self.assertEqual(items[0].document_date, "1404")
        self.assertEqual(items[2].document_type, "supreme_court_ruling_archive_bundle")

    def test_rejects_wrong_category_and_untrusted_page_host(self):
        connector = EkhtebarUnityRulingsConnector()
        self.assertEqual(list(connector.discover_from_html(self.html,
            "https://www.ekhtebar.ir/archive/", category="laws")), [])
        self.assertEqual(list(connector.discover_from_html(self.html,
            "https://ekhtebar.ir.evil.test/archive/", category="supreme_court_unity_rulings")), [])

    def test_respects_candidate_limit(self):
        from legal_bot.ingestion.policy import ConnectorPolicy
        connector = EkhtebarUnityRulingsConnector(ConnectorPolicy(max_candidates=1))
        items = list(connector.discover_from_html(self.html,
            "https://www.ekhtebar.ir/archive/", category="supreme_court_unity_rulings"))
        self.assertEqual(len(items), 1)


if __name__ == "__main__":
    unittest.main()
