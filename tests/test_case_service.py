import tempfile
from pathlib import Path

from legal_bot import db
from legal_bot.config import CASE_STORAGE_DIR
from legal_bot.core.cases import CaseService, CaseValidationError


def setup_module(module):
    module._old_db = db.DB_PATH
    module._tmp = tempfile.TemporaryDirectory()
    db.DB_PATH = Path(module._tmp.name) / "test.db"
    db.init_db()
    db.v193_upgrade(); db.v20_upgrade(); db.v67_upgrade()
    db.init_case_workspace_tables(); db.init_case_dates_table(); db.init_case_reminders_table()
    db.register_user(1001, "hash-a", "1234", full_name="A")
    db.register_user(2002, "hash-b", "5678", full_name="B")


def teardown_module(module):
    db.DB_PATH = module._old_db
    module._tmp.cleanup()


def test_create_and_ownership_boundary():
    svc = CaseService()
    case = svc.create(1001, "پرونده تست")
    assert case["user_id"] == 1001
    assert svc.get(1001, case["id"])["id"] == case["id"]
    assert svc.get(2002, case["id"]) is None
    assert svc.set_active(2002, case["id"]) is False


def test_create_empty_case_is_not_left_processing():
    svc = CaseService()
    case = svc.create_empty(1001, "پرونده خالی")
    assert case["status"] == "completed"
    assert svc.archive(1001, case["id"]) is True


def test_active_case_and_archive_rules():
    svc = CaseService()
    case = svc.create(1001, "پرونده آرشیو")
    assert svc.active(1001)["id"] == case["id"]
    # A processing case cannot be archived.
    assert svc.archive(1001, case["id"]) is False
    db.finish_case(case["id"], "ok")
    assert svc.archive(1001, case["id"]) is True
    assert svc.active(1001) is None
    assert svc.set_active(1001, case["id"]) is False
    assert svc.restore(1001, case["id"]) is True
    assert svc.set_active(1001, case["id"]) is True


def test_validation_and_note_limits():
    svc = CaseService()
    try:
        svc.create(1001, "")
        assert False, "empty case name must fail"
    except CaseValidationError:
        pass
    case = svc.create(1001, "یادداشت")
    assert svc.save_note(1001, case["id"], "سلام") is True
    assert svc.note(1001, case["id"])["note_text"] == "سلام"
    assert svc.note(2002, case["id"]) is None


def test_delete_is_user_scoped():
    svc = CaseService()
    case = svc.create(1001, "حذف")
    assert svc.delete(2002, case["id"]) is False
    assert svc.get(1001, case["id"]) is not None
    assert svc.delete(1001, case["id"]) is True
    assert svc.get(1001, case["id"]) is None


def test_case_update_search_and_archive_restore():
    svc = CaseService()
    case = svc.create_empty(1001, "پرونده قابل ویرایش")
    updated = svc.update(1001, case["id"], name="پرونده حقوقی مهم", stage="research", priority="high", next_action="بررسی قرارداد")
    assert updated["file_name"] == "پرونده حقوقی مهم"
    assert updated["stage"] == "research"
    assert updated["priority"] == "high"
    assert updated["next_action"] == "بررسی قرارداد"
    assert svc.list(1001, query="حقوقی")[0]["id"] == case["id"]
    assert svc.archive(1001, case["id"]) is True
    assert svc.list(1001, query="حقوقی") == []
    assert svc.list(1001, query="حقوقی", include_archived=True)[0]["status"] == "archived"
    assert svc.restore(1001, case["id"]) is True


def test_case_update_rejects_invalid_stage_priority():
    svc = CaseService()
    case = svc.create_empty(1001, "اعتبارسنجی")
    try:
        svc.update(1001, case["id"], stage="unknown")
        assert False, "invalid stage must fail"
    except CaseValidationError:
        pass
    try:
        svc.update(1001, case["id"], priority="critical")
        assert False, "invalid priority must fail"
    except CaseValidationError:
        pass
