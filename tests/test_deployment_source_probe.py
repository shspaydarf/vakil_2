from legal_bot.ingestion.deployment_source_probe import build_report
from legal_bot.ingestion.live_probe import _read
from legal_bot.ingestion.policy import ConnectorPolicy

def test_dotic_probe_reads_robots_before_page_and_never_downloads_assets():
    calls = []
    def reader(url, policy):
        calls.append(url)
        if url.endswith("/robots.txt"):
            return 200, "text/plain", b"User-agent: *\nAllow: /", url, ""
        return 200, "text/html; charset=utf-8", b"<html>record</html>", url, ""
    report = build_report(reader=reader)
    assert calls == ["https://dotic.ir/robots.txt", "https://dotic.ir/news/21843"]
    assert report["decision"] == "page_probe_ok_manual_source_review_required"
    assert report["policy"]["pdf_or_asset_downloads"] == 0
    assert report["policy"]["active_bank_write"] is False
    assert report["legal_authority_confirmed"] is False

def test_dotic_probe_fails_closed_when_robots_blocked():
    calls = []
    def reader(url, policy):
        calls.append(url)
        return 403, "text/html", b"forbidden", url, "HTTP 403"
    report = build_report(reader=reader)
    assert len(calls) == 1
    assert report["decision"] == "no_go_source_access_unverified_or_blocked"

def test_dotic_probe_does_not_fetch_page_when_robots_disallows():
    calls = []
    def reader(url, policy):
        calls.append(url)
        return 200, "text/plain", b"User-agent: *\nDisallow: /news/", url, ""
    report = build_report(reader=reader)
    assert len(calls) == 1
    assert report["source"]["page_status"] == "not_attempted_robots_disallow"

def test_http_redirect_is_rejected_by_reader(monkeypatch):
    class FakeResponse:
        status = 200
        headers = {"Content-Type": "text/html"}
        def geturl(self): return "http://dotic.ir/page"
        def read(self, n): return b"x"
        def __enter__(self): return self
        def __exit__(self, *args): pass
    monkeypatch.setattr("legal_bot.ingestion.live_probe.urlopen", lambda *a, **k: FakeResponse())
    status, ctype, body, final, error = _read("https://dotic.ir/page", ConnectorPolicy())
    assert status is None
    assert error == "redirect_outside_allowed_https_origin"
