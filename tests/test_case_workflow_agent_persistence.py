from pathlib import Path

from legal_bot import db
from legal_bot.core.cases import CaseService
from legal_bot.case_workflow_agent import create_case_workflow


def _boot(monkeypatch, tmp_path):
    db_path = tmp_path / "workflow-agent.sqlite3"
    monkeypatch.setattr(db, "DB_PATH", db_path)
    db.init_db(); db.v193_upgrade(); db.v20_upgrade(); db.v67_upgrade()
    db.init_case_workspace_tables(); db.init_case_workflow_agent_tables()
    db.register_user(88001, "hash-a", "1234", full_name="Lawyer A")
    db.register_user(88002, "hash-b", "5678", full_name="Lawyer B")
    case = CaseService().create_empty(88001, "پرونده گردش کار")
    return case


def test_workflow_checkpoint_survives_reload_and_is_owner_scoped(monkeypatch, tmp_path):
    case = _boot(monkeypatch, tmp_path)
    state = create_case_workflow(case["id"], "قرارداد")
    state["history"] = [{"type": "created", "detail": "created"}]
    db.save_case_workflow_agent_session(88001, case["id"], state)

    loaded = db.get_case_workflow_agent_session(88001, case["id"])
    assert loaded["state"]["current_step"] == "search"
    assert loaded["state"]["history"][0]["type"] == "created"
    assert db.get_case_workflow_agent_session(88002, case["id"]) is None


def test_workflow_checkpoint_can_be_cleared(monkeypatch, tmp_path):
    case = _boot(monkeypatch, tmp_path)
    db.save_case_workflow_agent_session(88001, case["id"], create_case_workflow(case["id"]))
    assert db.clear_case_workflow_agent_session(88001, case["id"]) is True
    assert db.get_case_workflow_agent_session(88001, case["id"]) is None


def test_workflow_checkpoint_compare_and_swap_rejects_stale_writes(monkeypatch, tmp_path):
    case = _boot(monkeypatch, tmp_path)
    initial = create_case_workflow(case["id"], "قرارداد")

    first = db.save_case_workflow_agent_session_if_unchanged(
        88001, case["id"], initial, expected_updated_at=None
    )
    assert first is not None

    stale_state = dict(first["state"])
    stale_state["query"] = "درخواست قدیمی"
    changed_state = dict(first["state"])
    changed_state["query"] = "درخواست جدید"

    second = db.save_case_workflow_agent_session_if_unchanged(
        88001, case["id"], changed_state,
        expected_updated_at=first["updated_at"],
    )
    assert second is not None

    rejected = db.save_case_workflow_agent_session_if_unchanged(
        88001, case["id"], stale_state,
        expected_updated_at=first["updated_at"],
    )
    assert rejected is None
    assert db.get_case_workflow_agent_session(88001, case["id"])["state"]["query"] == "درخواست جدید"


def test_workflow_checkpoint_compare_and_swap_does_not_overwrite_existing_session(monkeypatch, tmp_path):
    case = _boot(monkeypatch, tmp_path)
    state = create_case_workflow(case["id"], "اول")
    created = db.save_case_workflow_agent_session_if_unchanged(
        88001, case["id"], state, expected_updated_at=None
    )
    assert created is not None

    competing = create_case_workflow(case["id"], "دوم")
    rejected = db.save_case_workflow_agent_session_if_unchanged(
        88001, case["id"], competing, expected_updated_at=None
    )
    assert rejected is None
    assert db.get_case_workflow_agent_session(88001, case["id"])["state"]["query"] == "اول"
