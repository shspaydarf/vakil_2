from legal_bot.ingestion.phase8_3_download_trial import build_download_trial, validate_download_trial

URL = "https://www.ekhtebar.ir/wp-content/uploads/2020/06/sample.pdf"

def test_phase_is_8_3():
    assert build_download_trial(outcome="blocked_dns", detail="DNS unavailable", source_url=URL)["phase"] == "8.3"

def test_secondary_source_is_explicit():
    report = build_download_trial(outcome="blocked_dns", detail="DNS unavailable", source_url=URL)
    assert report["evidence"]["source_role"] == "secondary_reference_only"

def test_no_download_or_staging_claimed():
    report = build_download_trial(outcome="blocked_dns", detail="DNS unavailable", source_url=URL)
    assert report["evidence"]["downloaded"] is False
    assert report["evidence"]["staged"] is False

def test_valid_report_hash():
    report = build_download_trial(outcome="blocked_dns", detail="DNS unavailable", source_url=URL)
    assert validate_download_trial(report)

def test_tampering_is_rejected():
    report = build_download_trial(outcome="blocked_dns", detail="DNS unavailable", source_url=URL)
    report["evidence"]["downloaded"] = True
    assert not validate_download_trial(report)
