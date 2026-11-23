import unittest
from pathlib import Path
from legal_bot.ingestion.connectors.majles_rc import MajlesResearchCenterConnector
from legal_bot.ingestion.policy import ConnectorPolicy


class MajlesConnectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = Path(__file__).parent / "fixtures/ingestion/majles_law_search_sample.html"
        cls.html = fixture.read_text(encoding="utf-8")

    def test_discovers_record_pages_and_pdf_without_duplicates(self):
        items = list(MajlesResearchCenterConnector().discover_from_html(
            self.html, "https://rc.majlis.ir/fa/law", category="parliamentary_laws"))
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0].source_record_id, "95227")
        self.assertEqual(items[1].source_record_id, "95202")
        self.assertEqual(items[2].asset_url, "https://rc.majlis.ir/files/law-1402.pdf")
        self.assertEqual(items[2].document_date, "1402")
        self.assertTrue(all(x.discovery_status == "discovered" for x in items))

    def test_rejects_untrusted_host_and_unknown_category(self):
        connector = MajlesResearchCenterConnector()
        self.assertEqual(list(connector.discover_from_html(self.html,
            "https://rc.majlis.ir.evil.test/fa/law", category="laws")), [])
        self.assertEqual(list(connector.discover_from_html(self.html,
            "https://rc.majlis.ir/fa/law", category="court_rulings")), [])

    def test_candidate_limit(self):
        connector = MajlesResearchCenterConnector(ConnectorPolicy(max_candidates=1))
        self.assertEqual(len(list(connector.discover_from_html(self.html,
            "https://rc.majlis.ir/fa/law", category="laws"))), 1)


if __name__ == "__main__":
    unittest.main()
