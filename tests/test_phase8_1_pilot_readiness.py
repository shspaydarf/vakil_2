from copy import deepcopy

from legal_bot.ingestion.phase8_1_pilot_readiness import (
    build_phase8_1_plan, validate_phase8_1_plan,
)


def test_phase8_1_plan_is_valid_and_bounded():
    plan = build_phase8_1_plan()
    assert validate_phase8_1_plan(plan)
    assert len(plan["targets"]) == 1
    assert plan["targets"][0]["record_id"] == "93849"
    assert plan["limits"]["pdf_downloaded"] is False
    assert plan["limits"]["active_bank_modified"] is False


def test_phase8_1_rejects_non_allowlisted_host():
    plan = build_phase8_1_plan()
    plan["targets"][0]["record_url"] = "https://example.com/fa/law/show/93849"
    assert not validate_phase8_1_plan(plan)


def test_phase8_1_rejects_active_bank_mutation_claim():
    plan = build_phase8_1_plan()
    plan["limits"]["active_bank_modified"] = True
    assert not validate_phase8_1_plan(plan)


def test_phase8_1_rejects_tampered_hash():
    plan = build_phase8_1_plan()
    plan["targets"][0]["title"] = "عنوان دستکاری‌شده"
    assert not validate_phase8_1_plan(plan)


def test_phase8_1_keeps_ekhtebar_secondary():
    plan = build_phase8_1_plan()
    assert plan["limits"]["secondary_source_may_replace_official"] is False
    assert all(item["source_id"] != "ekhtebar" or item["outcome"] == "javascript_challenge"
               for item in plan["observations"])
