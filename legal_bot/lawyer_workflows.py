"""Private, persistent lawyer workflow templates and supervised run progress."""
from __future__ import annotations
import json, uuid
from typing import Any, Dict, List
from .db import conn, now_iso, get_case
from .workflow_templates import list_workflow_templates

ACTIONS = {"workspace", "documents", "review", "ai", "drafting"}
MAX_TEMPLATES = 50
MAX_STEPS = 12

def init_lawyer_workflows():
    with conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS lawyer_workflows (
            id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, title TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT '', description TEXT NOT NULL DEFAULT '',
            steps_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE)""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_lawyer_workflows_user ON lawyer_workflows(user_id, updated_at DESC)")
        c.execute("""CREATE TABLE IF NOT EXISTS lawyer_workflow_runs (
            id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, case_id INTEGER NOT NULL,
            workflow_id TEXT NOT NULL, workflow_snapshot TEXT NOT NULL,
            completed_json TEXT NOT NULL DEFAULT '[]', status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE,
            FOREIGN KEY(case_id) REFERENCES cases(id) ON DELETE CASCADE)""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_lawyer_workflow_runs_user ON lawyer_workflow_runs(user_id, updated_at DESC)")
        c.commit()

def _clean(data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(data, dict): raise ValueError("اطلاعات گردش‌کار نامعتبر است.")
    title=str(data.get("title") or "").strip(); category=str(data.get("category") or "عمومی").strip()
    description=str(data.get("description") or "").strip(); steps=data.get("steps")
    if not title or len(title)>100: raise ValueError("عنوان الزامی است و حداکثر ۱۰۰ نویسه مجاز است.")
    if len(category)>60 or len(description)>240: raise ValueError("دسته‌بندی یا توضیح بیش از حد طولانی است.")
    if not isinstance(steps,list) or not 2<=len(steps)<=MAX_STEPS: raise ValueError("گردش‌کار باید بین ۲ تا ۱۲ مرحله داشته باشد.")
    cleaned=[]
    for i,step in enumerate(steps):
        if not isinstance(step,dict): raise ValueError(f"مرحله {i+1} نامعتبر است.")
        st=str(step.get("title") or "").strip(); action=str(step.get("action") or "workspace").strip().lower()
        instruction=str(step.get("instruction") or "").strip(); prompt=str(step.get("prompt") or "").strip()
        if not st or len(st)>100: raise ValueError(f"عنوان مرحله {i+1} الزامی و حداکثر ۱۰۰ نویسه است.")
        if action not in ACTIONS: raise ValueError(f"ابزار مرحله {i+1} مجاز نیست.")
        if not instruction or len(instruction)>1000: raise ValueError(f"راهنمای مرحله {i+1} الزامی و حداکثر ۱۰۰۰ نویسه است.")
        if len(prompt)>4000: raise ValueError(f"دستور هوش مصنوعی مرحله {i+1} بیش از حد طولانی است.")
        if action=="ai" and not prompt: raise ValueError(f"مرحله هوش مصنوعی {i+1} باید دستور قابل بازبینی داشته باشد.")
        cleaned.append({"title":st,"action":action,"instruction":instruction,**({"prompt":prompt} if action=="ai" else {})})
    return {"title":title,"category":category,"description":description,"steps":cleaned}

def list_lawyer_workflows(uid: int) -> List[Dict[str, Any]]:
    init_lawyer_workflows()
    with conn() as c: rows=c.execute("SELECT * FROM lawyer_workflows WHERE user_id=? ORDER BY updated_at DESC LIMIT ?",(int(uid),MAX_TEMPLATES)).fetchall()
    own=[]
    for r in rows:
        x=dict(r); x["steps"]=json.loads(x.pop("steps_json")); x["source"]="personal"; own.append(x)
    return [{**x, "source": "starter"} for x in list_workflow_templates()]+own

def create_lawyer_workflow(uid: int, data: Dict[str, Any]) -> Dict[str, Any]:
    init_lawyer_workflows(); item=_clean(data); ts=now_iso(); wid=uuid.uuid4().hex
    with conn() as c:
        n=c.execute("SELECT COUNT(*) n FROM lawyer_workflows WHERE user_id=?",(int(uid),)).fetchone()["n"]
        if n>=MAX_TEMPLATES: raise ValueError("حداکثر ۵۰ گردش‌کار اختصاصی مجاز است.")
        c.execute("INSERT INTO lawyer_workflows(id,user_id,title,category,description,steps_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
            (wid,int(uid),item["title"],item["category"],item["description"],json.dumps(item["steps"],ensure_ascii=False),ts,ts)); c.commit()
    return {"id":wid,**item,"created_at":ts,"updated_at":ts,"source":"personal"}

def update_lawyer_workflow(uid: int, wid: str, data: Dict[str, Any]):
    init_lawyer_workflows(); item=_clean(data); ts=now_iso()
    with conn() as c:
        cur=c.execute("UPDATE lawyer_workflows SET title=?,category=?,description=?,steps_json=?,updated_at=? WHERE id=? AND user_id=?",
          (item["title"],item["category"],item["description"],json.dumps(item["steps"],ensure_ascii=False),ts,str(wid)[:80],int(uid)))
        if cur.rowcount!=1: return None
        c.commit()
    return {"id":wid,**item,"updated_at":ts,"source":"personal"}

def delete_lawyer_workflow(uid: int, wid: str) -> bool:
    init_lawyer_workflows()
    with conn() as c:
        cur=c.execute("DELETE FROM lawyer_workflows WHERE id=? AND user_id=?",(str(wid)[:80],int(uid))); c.commit(); return cur.rowcount==1

def start_workflow_run(uid: int, case_id: int, workflow_id: str) -> Dict[str, Any]:
    init_lawyer_workflows(); case=get_case(int(uid),int(case_id))
    if not case: raise ValueError("پرونده پیدا نشد یا متعلق به این حساب نیست.")
    if str(case.get("status") or "").lower()=="archived": raise ValueError("برای پرونده بایگانی‌شده نمی‌توان گردش‌کار تازه آغاز کرد.")
    template=next((x for x in list_workflow_templates() if x["id"]==workflow_id),None)
    if not template:
        with conn() as c: row=c.execute("SELECT * FROM lawyer_workflows WHERE id=? AND user_id=?",(str(workflow_id)[:80],int(uid))).fetchone()
        if row:
            template={"id":row["id"],"title":row["title"],"category":row["category"],"description":row["description"],"steps":json.loads(row["steps_json"])}
    if not template: raise ValueError("گردش‌کار پیدا نشد یا متعلق به این حساب نیست.")
    ts=now_iso(); rid=uuid.uuid4().hex
    with conn() as c:
        c.execute("INSERT INTO lawyer_workflow_runs(id,user_id,case_id,workflow_id,workflow_snapshot,completed_json,status,created_at,updated_at) VALUES(?,?,?,?,?,'[]','active',?,?)",
          (rid,int(uid),int(case_id),str(workflow_id),json.dumps(template,ensure_ascii=False),ts,ts)); c.commit()
    return {"id":rid,"case_id":int(case_id),"template":template,"completed":[],"status":"active","created_at":ts,"updated_at":ts}

def list_workflow_runs(uid: int, case_id: int | None=None) -> List[Dict[str, Any]]:
    init_lawyer_workflows()
    with conn() as c:
        if case_id is None: rows=c.execute("SELECT * FROM lawyer_workflow_runs WHERE user_id=? AND status='active' ORDER BY updated_at DESC LIMIT 20",(int(uid),)).fetchall()
        else: rows=c.execute("SELECT * FROM lawyer_workflow_runs WHERE user_id=? AND case_id=? AND status='active' ORDER BY updated_at DESC LIMIT 20",(int(uid),int(case_id))).fetchall()
    out=[]
    for r in rows:
        x=dict(r); x["template"]=json.loads(x.pop("workflow_snapshot")); x["completed"]=json.loads(x.pop("completed_json")); out.append(x)
    return out

def update_workflow_run(uid: int, run_id: str, completed: Any, status: str="active"):
    init_lawyer_workflows()
    if not isinstance(completed,list) or len(completed)>MAX_STEPS or any(type(i) is not int or i<0 for i in completed): raise ValueError("وضعیت مراحل نامعتبر است.")
    status=str(status or "active").lower()
    if status not in {"active","completed"}: raise ValueError("وضعیت گردش‌کار نامعتبر است.")
    ts=now_iso()
    with conn() as c:
        row=c.execute("SELECT workflow_snapshot FROM lawyer_workflow_runs WHERE id=? AND user_id=?",(str(run_id)[:80],int(uid))).fetchone()
        if not row: return None
        template=json.loads(row["workflow_snapshot"])
        if any(i>=len(template.get("steps",[])) for i in completed): raise ValueError("شماره مرحله خارج از محدوده است.")
        if status=="completed" and len(set(completed))!=len(template.get("steps",[])): raise ValueError("برای پایان گردش‌کار، همه مراحل باید تکمیل شوند.")
        c.execute("UPDATE lawyer_workflow_runs SET completed_json=?,status=?,updated_at=? WHERE id=? AND user_id=?",
          (json.dumps(sorted(set(completed))),status,ts,str(run_id)[:80],int(uid))); c.commit()
        return {"id":run_id,"completed":sorted(set(completed)),"status":status,"updated_at":ts}
