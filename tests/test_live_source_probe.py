import unittest
from legal_bot.ingestion.live_probe import probe_source
from legal_bot.ingestion.policy import ConnectorPolicy

class LiveProbeTests(unittest.TestCase):
    def setUp(self):
        self.source = {"source_id":"ekhtebar", "base_url":"https://www.ekhtebar.ir/",
                      "pilot_url":"https://www.ekhtebar.ir/archive/", "allowed_hosts":["www.ekhtebar.ir"]}
        self.policy = ConnectorPolicy(user_agent="MACHINA-TestBot/1.0")

    def test_robots_disallow_stops_before_page(self):
        calls=[]
        def reader(url, policy):
            calls.append(url)
            return (200, "text/plain", b"User-agent: *\nDisallow: /archive/", url, "")
        result=probe_source(self.source, self.policy, reader=reader)
        self.assertEqual(result.page_status, "not_attempted_robots_disallow")
        self.assertEqual(len(calls), 1)

    def test_page_checked_after_robots_allows(self):
        calls=[]
        def reader(url, policy):
            calls.append(url)
            if url.endswith("robots.txt"):
                return (200, "text/plain", b"User-agent: *\nAllow: /", url, "")
            return (200, "text/html; charset=utf-8", b"<html>archive</html>", url, "")
        result=probe_source(self.source, self.policy, reader=reader)
        self.assertEqual(result.page_status, "ok")
        self.assertEqual(len(calls), 2)

    def test_robots_failure_stops(self):
        def reader(url, policy):
            return (403, "text/html", b"", url, "blocked")
        result=probe_source(self.source, self.policy, reader=reader)
        self.assertEqual(result.page_status, "not_attempted")

if __name__ == '__main__':
    unittest.main()
