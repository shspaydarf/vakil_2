from legal_bot.ingestion import deployment_diagnostics as dd


def test_default_target_is_dotic_official_primary():
    assert dd.SOURCE_TARGETS["dotic"]["url"] == "https://dotic.ir/"
    assert dd.SOURCE_TARGETS["dotic"]["role"] == "official_primary"


def test_report_marks_all_side_effects_disabled(monkeypatch):
    def fake(url, timeout=4.0):
        return type("R", (), {"to_dict": lambda self: {"host": "dotic.ir", "status": "dns_failed"}})()
    monkeypatch.setattr(dd, "diagnose_host", fake)
    report = dd.build_report(["dotic"])
    assert report["policy"]["http_requests_sent"] is False
    assert report["policy"]["active_bank_write"] is False
    assert report["policy"]["scheduler_enabled"] is False
    assert report["decision"] == "no_go_live_acquisition"


def test_secondary_source_cannot_make_official_gate_pass(monkeypatch):
    def fake(url, timeout=4.0):
        return type("R", (), {"to_dict": lambda self: {"host": "example", "status": "tls_ok_http_not_tested"}})()
    monkeypatch.setattr(dd, "diagnose_host", fake)
    report = dd.build_report(["dotic", "ekhtebar"])
    assert report["decision"] == "tls_ready_for_next_source_review"
    assert report["sources"][1]["role"] == "secondary_discovery_only"


def test_cli_rejects_unbounded_timeout():
    try:
        dd.main(["--source", "dotic", "--timeout", "99", "--output", "/tmp/should-not-exist.json"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("expected argparse rejection")
