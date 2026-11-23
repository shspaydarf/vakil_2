from datetime import datetime, timezone
from pathlib import Path
import pytest
from legal_bot import db
from legal_bot.lawyer_workflows import (
    create_lawyer_workflow, list_lawyer_workflows, update_lawyer_workflow,
    delete_lawyer_workflow, start_workflow_run, list_workflow_runs,
    update_workflow_run,
)


def _seed(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "lawyer-workflows.sqlite3")
    db.init_db(); now=datetime.now(timezone.utc).isoformat()
    with db.conn() as c:
        for uid in (811, 812):
            c.execute("INSERT INTO users(user_id,free_month,created_at) VALUES(?,?,?)",(uid,"2026-10",now))
        c.execute("INSERT INTO cases(user_id,file_name,status,created_at) VALUES(?,?,?,?)",(811,"پرونده آزمایشی","active",now))
        c.commit()
    with db.conn() as c: return c.execute("SELECT id FROM cases WHERE user_id=811").fetchone()[0]


def _payload(title="گردش‌کار اختصاصی"):
    return {"title":title,"category":"قرارداد","description":"مسیر تست","steps":[
        {"title":"مرور سند","action":"documents","instruction":"سندهای پرونده را مرور کن."},
        {"title":"تحلیل کنترل‌شده","action":"ai","instruction":"دستور را بازبینی کن.","prompt":"فقط بر اساس متن سند تحلیل کن و هیچ واقعیتی نساز."},
    ]}


def test_personal_workflows_are_private_validated_and_editable(monkeypatch,tmp_path):
    _seed(monkeypatch,tmp_path)
    item=create_lawyer_workflow(811,_payload())
    assert item["source"]=="personal"
    assert any(x["id"]==item["id"] for x in list_lawyer_workflows(811))
    assert all(x["id"]!=item["id"] for x in list_lawyer_workflows(812))
    updated=update_lawyer_workflow(811,item["id"],_payload("نسخه ویرایش‌شده"))
    assert updated["title"]=="نسخه ویرایش‌شده"
    assert update_lawyer_workflow(812,item["id"],_payload()) is None
    assert delete_lawyer_workflow(812,item["id"]) is False
    assert delete_lawyer_workflow(811,item["id"]) is True


def test_workflow_builder_rejects_bad_ai_steps_and_oversized_lists(monkeypatch,tmp_path):
    _seed(monkeypatch,tmp_path)
    bad=_payload();bad["steps"][1].pop("prompt")
    with pytest.raises(ValueError): create_lawyer_workflow(811,bad)
    bad=_payload();bad["steps"]=[bad["steps"][0]]
    with pytest.raises(ValueError): create_lawyer_workflow(811,bad)
    bad=_payload();bad["steps"][0]["action"]="delete_database"
    with pytest.raises(ValueError): create_lawyer_workflow(811,bad)


def test_workflow_run_progress_survives_reload_and_is_case_user_scoped(monkeypatch,tmp_path):
    cid=_seed(monkeypatch,tmp_path)
    item=create_lawyer_workflow(811,_payload())
    run=start_workflow_run(811,cid,item["id"])
    assert run["completed"]==[]
    assert len(list_workflow_runs(811,cid))==1
    assert list_workflow_runs(812,cid)==[]
    updated=update_workflow_run(811,run["id"],[0],"active")
    assert updated["completed"]==[0]
    assert list_workflow_runs(811,cid)[0]["completed"]==[0]
    with pytest.raises(ValueError): update_workflow_run(811,run["id"],[0],"completed")
    finished=update_workflow_run(811,run["id"],[0,1],"completed")
    assert finished["status"]=="completed"
    assert list_workflow_runs(811,cid)==[]
    with pytest.raises(ValueError): start_workflow_run(812,cid,item["id"])


def test_ai_features_are_grouped_in_ai_submenu_and_workflow_builder_is_integrated():
    root=Path(__file__).resolve().parents[1]
    html=(root/"miniapp/index.html").read_text(encoding="utf-8")
    app=(root/"miniapp/app.js").read_text(encoding="utf-8")
    assert 'id="aiSubmenu"' in html and 'id="openAiSubmenu"' in html
    assert 'id="workflowCreate"' in html
    assert html.index('id="aiSubmenu"') < html.index('class="work-products-section"') < html.index('class="recent-activity-section"')
    assert "openWorkflowBuilder" in app and "/api/v1/lawyer-workflows" in app
    assert "/api/v1/workflow-runs" in app
    assert 'data-nav="' in html
    assert 'id="workflowTemplatesPane"' not in html
