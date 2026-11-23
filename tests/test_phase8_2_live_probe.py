from copy import deepcopy
from legal_bot.ingestion.phase8_2_live_probe import build_phase8_2_report, validate_phase8_2_report


def test_phase8_2_report_is_valid_and_records_pdf_sample():
    report = build_phase8_2_report()
    assert validate_phase8_2_report(report)
    pdf = next(x for x in report["evidence"] if x["source_id"] == "ekhtebar_pdf_sample")
    assert pdf["document_pages"] == 7
    assert report["findings"]["ekhtebar_listing_and_direct_pdf_route_observed"] is True


def test_phase8_2_does_not_promote_ekhtebar_to_primary():
    report = build_phase8_2_report()
    assert report["findings"]["ekhtebar_is_secondary_only"] is True
    assert all(x["source_role"] != "official_primary_candidate" for x in report["evidence"] if x["source_id"].startswith("ekhtebar"))


def test_phase8_2_does_not_claim_majles_connection():
    report = build_phase8_2_report()
    assert report["findings"]["majles_live_route_confirmed"] is False
    assert report["findings"]["project_runtime_connectivity_proven"] is False


def test_phase8_2_rejects_active_bank_mutation_claim():
    report = build_phase8_2_report()
    report["findings"]["active_bank_modified"] = True
    assert not validate_phase8_2_report(report)


def test_phase8_2_rejects_tampering():
    report = build_phase8_2_report()
    report["evidence"][0]["detail"] = "tampered"
    assert not validate_phase8_2_report(report)
