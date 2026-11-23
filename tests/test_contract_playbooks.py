from legal_bot.contract_playbooks import (
    build_playbook_checklist,
    get_contract_playbook,
    list_contract_playbooks,
)


def test_three_builtin_playbooks_are_available():
    items = list_contract_playbooks()
    assert {item["id"] for item in items} == {"construction", "lease", "sale"}
    assert all(item["title"] and item["description"] for item in items)


def test_each_playbook_has_unique_nonempty_criteria_and_questions():
    for item in list_contract_playbooks():
        playbook = get_contract_playbook(item["id"])
        ids = [criterion_id for criterion_id, _ in playbook["criteria"]]
        assert len(ids) == len(set(ids))
        assert len(ids) >= 8
        assert all(label.strip() for _, label in playbook["criteria"])
        assert playbook["follow_up_questions"]
        assert playbook["risk_focus"]


def test_checklist_is_normalized_and_evidence_starts_empty():
    checklist = build_playbook_checklist("lease")
    assert checklist["playbook_id"] == "lease"
    assert checklist["criteria"]
    assert all(row["status"] == "نیازمند بررسی" and row["evidence"] == [] for row in checklist["criteria"])
    assert "قطعی" in checklist["notice"]


def test_unknown_playbook_returns_none():
    assert get_contract_playbook("unknown") is None
    assert build_playbook_checklist("unknown") is None


def test_returned_playbook_is_detached_from_internal_definition():
    playbook = get_contract_playbook("sale")
    playbook["follow_up_questions"] = ("دستکاری",)
    assert get_contract_playbook("sale")["follow_up_questions"] != ("دستکاری",)
