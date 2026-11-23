
import tempfile
from pathlib import Path

def test_drafting_api_routes_and_artifact_init(monkeypatch):
    td=tempfile.TemporaryDirectory()
    try:
        db_path=str(Path(td.name)/"api.sqlite3")
        monkeypatch.setenv("DB_PATH",db_path)
        from legal_bot import db
        db.DB_PATH=db_path
        db.init_db(); db.v193_upgrade(); db.v20_upgrade(); db.v67_upgrade()
        db.init_case_workspace_tables(); db.init_case_dates_table(); db.init_case_reminders_table(); db.init_drafting_workflow_tables()
        from legal_bot.api import APIHandler
        import inspect
        assert '/drafts' in inspect.getsource(APIHandler.do_GET)
        assert '/draft' in inspect.getsource(APIHandler.do_POST)
        from legal_bot.drafting_artifacts import init_drafting_artifact_tables
        init_drafting_artifact_tables()
    finally:
        td.cleanup()
