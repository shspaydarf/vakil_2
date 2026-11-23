import pytest
from legal_bot.ingestion.phase9_1_acquisition_policy import build_acquisition_plan, validate_acquisition_plan

MAJLES = "https://rc.majlis.ir/fa/law/show/93849"
EKHTEBAR = "https://www.ekhtebar.ir/wp-content/uploads/sample.pdf"

def test_majles_defaults_to_html_candidate_and_defers_print_automation():
    plan = build_acquisition_plan("majles_rc", MAJLES)
    assert plan["route"]["route"] == "official_html_capture_candidate"
    assert plan["safety"]["print_workflow_automation_enabled"] is False
    assert validate_acquisition_plan(plan)

def test_observed_primary_pdf_uses_official_pdf_class():
    plan = build_acquisition_plan("majles_rc", MAJLES, direct_pdf_observed=True)
    assert plan["route"]["output_class"] == "official_pdf"
    assert validate_acquisition_plan(plan)

def test_ekhtebar_is_always_secondary_even_with_direct_pdf():
    plan = build_acquisition_plan("ekhtebar", EKHTEBAR, direct_pdf_observed=True)
    assert plan["route"]["source_role"] == "secondary_reference_only"
    assert plan["route"]["output_class"] == "secondary_pdf_quarantine_only"
    assert validate_acquisition_plan(plan)

def test_rejects_non_allowlisted_host():
    with pytest.raises(ValueError):
        build_acquisition_plan("majles_rc", "https://example.com/law")

def test_rejects_unknown_source():
    with pytest.raises(ValueError):
        build_acquisition_plan("unknown", MAJLES)

def test_tampered_plan_is_rejected():
    plan = build_acquisition_plan("ekhtebar", EKHTEBAR)
    plan["safety"]["active_bank_modified"] = True
    assert not validate_acquisition_plan(plan)


def test_non_www_ekhtebar_host_matches_connector_allowlist():
    plan = build_acquisition_plan("ekhtebar", "https://ekhtebar.ir/wp-content/uploads/sample.pdf", direct_pdf_observed=True)
    assert plan["route"]["source_role"] == "secondary_reference_only"
    assert validate_acquisition_plan(plan)


def test_source_hosts_cannot_be_crossed():
    with pytest.raises(ValueError):
        build_acquisition_plan("majles_rc", "https://www.ekhtebar.ir/law.pdf", direct_pdf_observed=True)
    with pytest.raises(ValueError):
        build_acquisition_plan("ekhtebar", "https://rc.majlis.ir/law.pdf", direct_pdf_observed=True)


def test_rejects_credentials_and_nonstandard_ports():
    with pytest.raises(ValueError):
        build_acquisition_plan("majles_rc", "https://user:pass@rc.majlis.ir/law.pdf", direct_pdf_observed=True)
    with pytest.raises(ValueError):
        build_acquisition_plan("majles_rc", "https://rc.majlis.ir:8443/law.pdf", direct_pdf_observed=True)
