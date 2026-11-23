"""Durable, case-owned drafting artifacts for DRAFT-01.

An artifact is the user-facing draft produced by the unified drafting workflow.
Workflow checkpoints remain separate: this table stores the actual draft/output
so the product can later expose it through the API and Mini App without relying
on Telegram's in-memory state.
"""
from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional

from .db import conn, get_case, now_iso, init_case_ai_history_table

VERSION = 1


def init_drafting_artifact_tables() -> None:
    with conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS drafting_artifacts (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            case_id INTEGER NOT NULL,
            version_no INTEGER NOT NULL,
            status TEXT NOT NULL,
            brief_type TEXT NOT NULL DEFAULT 'لایحه دفاعیه',
            draft_text TEXT NOT NULL DEFAULT '',
            gate_json TEXT NOT NULL DEFAULT '{}',
            output_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE,
            FOREIGN KEY(case_id) REFERENCES cases(id) ON DELETE CASCADE,
            UNIQUE(user_id, case_id, version_no)
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_drafting_artifacts_case ON drafting_artifacts(user_id, case_id, version_no DESC)")
        # Review actions are append-only events; the draft artifact itself stays immutable.
        c.execute("""CREATE TABLE IF NOT EXISTS drafting_review_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            artifact_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            case_id INTEGER NOT NULL,
            decision TEXT NOT NULL CHECK(decision IN ('reviewed_ok', 'changes_requested')),
            note TEXT NOT NULL DEFAULT '',
            confirmed INTEGER NOT NULL DEFAULT 0 CHECK(confirmed IN (0,1)),
            created_at TEXT NOT NULL,
            FOREIGN KEY(artifact_id) REFERENCES drafting_artifacts(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE,
            FOREIGN KEY(case_id) REFERENCES cases(id) ON DELETE CASCADE
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_drafting_reviews_artifact ON drafting_review_events(user_id, case_id, artifact_id, id DESC)")


def _json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, separators=(",", ":"), default=str)


def _decode(value: str) -> Any:
    try:
        return json.loads(value or "{}")
    except Exception:
        return {}


def _owned_case(uid: int, cid: int) -> bool:
    return bool(get_case(int(uid), int(cid)))


def save_draft_artifact(uid: int, cid: int, *, status: str, draft_text: str,
                        gate: Optional[Dict[str, Any]] = None,
                        output: Optional[Dict[str, Any]] = None,
                        brief_type: str = "لایحه دفاعیه") -> Dict[str, Any]:
    """Create a new immutable draft version for an owned case."""
    init_drafting_artifact_tables()
    case = get_case(int(uid), int(cid))
    if not case:
        raise ValueError("case_not_found")
    if str(case.get("status") or "").lower() == "archived":
        raise ValueError("case_archived")
    ts = now_iso()
    artifact_id = uuid.uuid4().hex
    with conn() as c:
        # Serialize version allocation so concurrent draft requests cannot
        # calculate the same next version number.
        c.execute("BEGIN IMMEDIATE")
        row = c.execute(
            "SELECT COALESCE(MAX(version_no), 0) AS n FROM drafting_artifacts WHERE user_id=? AND case_id=?",
            (int(uid), int(cid)),
        ).fetchone()
        version_no = int(row["n"] or 0) + 1
        c.execute("""INSERT INTO drafting_artifacts
            (id,user_id,case_id,version_no,status,brief_type,draft_text,gate_json,output_json,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (artifact_id, int(uid), int(cid), version_no, str(status), str(brief_type or "لایحه دفاعیه"),
             str(draft_text or ""), _json(gate), _json(output), ts, ts))
        c.commit()
    return get_draft_artifact(uid, cid, artifact_id) or {}


def get_draft_artifact(uid: int, cid: int, artifact_id: str) -> Optional[Dict[str, Any]]:
    init_drafting_artifact_tables()
    with conn() as c:
        row = c.execute("""SELECT * FROM drafting_artifacts
            WHERE id=? AND user_id=? AND case_id=?""", (str(artifact_id), int(uid), int(cid))).fetchone()
    return _row(row) if row else None


def latest_draft_artifact(uid: int, cid: int) -> Optional[Dict[str, Any]]:
    init_drafting_artifact_tables()
    if not _owned_case(uid, cid):
        return None
    with conn() as c:
        row = c.execute("""SELECT * FROM drafting_artifacts
            WHERE user_id=? AND case_id=? ORDER BY version_no DESC LIMIT 1""", (int(uid), int(cid))).fetchone()
    return _row(row) if row else None


def list_draft_artifacts(uid: int, cid: int, limit: int = 12) -> List[Dict[str, Any]]:
    init_drafting_artifact_tables()
    if not _owned_case(uid, cid):
        return []
    with conn() as c:
        rows = c.execute("""SELECT * FROM drafting_artifacts
            WHERE user_id=? AND case_id=? ORDER BY version_no DESC LIMIT ?""", (int(uid), int(cid), max(1, int(limit)))).fetchall()
    return [_row(r) for r in rows]


def _row(row) -> Dict[str, Any]:
    d = dict(row)
    d["version_no"] = int(d.get("version_no") or 0)
    d["gate"] = _decode(d.pop("gate_json", "{}"))
    d["output"] = _decode(d.pop("output_json", "{}"))
    return d


def record_draft_review(uid: int, cid: int, artifact_id: str, *, decision: str, note: str = "", confirm_review: bool = False) -> Dict[str, Any]:
    """Append an explicit review event without changing the immutable draft.

    This records the signed-in account's action only; it does not verify professional
    status, identity beyond the app authentication, or legal correctness.
    """
    uid, cid = int(uid), int(cid)
    decision = str(decision or "").strip().lower()
    if decision not in {"reviewed_ok", "changes_requested"}:
        raise ValueError("review_decision_invalid")
    note = str(note or "").strip()
    if len(note) > 8000:
        raise ValueError("review_note_too_long")
    if confirm_review is not True:
        raise ValueError("review_confirmation_required")
    item = get_draft_artifact(uid, cid, str(artifact_id))
    if not item:
        raise ValueError("draft_not_found")
    case = get_case(uid, cid)
    if not case:
        raise ValueError("case_not_found")
    if str(case.get("status") or "").lower() == "archived":
        raise ValueError("case_archived")
    ts = now_iso()
    with conn() as c:
        c.execute("""INSERT INTO drafting_review_events
            (artifact_id,user_id,case_id,decision,note,confirmed,created_at)
            VALUES (?,?,?,?,?,?,?)""",
            (str(artifact_id), uid, cid, decision, note, 1, ts))
        event_id = c.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
        c.commit()
    return get_draft_review(uid, cid, str(artifact_id), int(event_id)) or {}


def list_draft_reviews(uid: int, cid: int, artifact_id: str, limit: int = 30) -> List[Dict[str, Any]]:
    """List review events only when both case and artifact are owned by the user."""
    if not get_draft_artifact(int(uid), int(cid), str(artifact_id)):
        return []
    with conn() as c:
        rows = c.execute("""SELECT id,artifact_id,user_id,case_id,decision,note,confirmed,created_at
            FROM drafting_review_events WHERE user_id=? AND case_id=? AND artifact_id=?
            ORDER BY id DESC LIMIT ?""", (int(uid), int(cid), str(artifact_id), max(1, min(100, int(limit))))).fetchall()
    return [dict(r) for r in rows]


def get_draft_review(uid: int, cid: int, artifact_id: str, review_id: int) -> Optional[Dict[str, Any]]:
    if not get_draft_artifact(int(uid), int(cid), str(artifact_id)):
        return None
    with conn() as c:
        row = c.execute("""SELECT id,artifact_id,user_id,case_id,decision,note,confirmed,created_at
            FROM drafting_review_events WHERE id=? AND user_id=? AND case_id=? AND artifact_id=?""",
            (int(review_id), int(uid), int(cid), str(artifact_id))).fetchone()
    return dict(row) if row else None


def init_work_product_bookmarks() -> None:
    """Per-lawyer bookmarks for persisted AI exchanges and draft artifacts."""
    with conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS lawyer_saved_work_products (
            user_id INTEGER NOT NULL,
            case_id INTEGER NOT NULL,
            item_type TEXT NOT NULL CHECK(item_type IN ('ai','draft')),
            item_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(user_id, item_type, item_id),
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE,
            FOREIGN KEY(case_id) REFERENCES cases(id) ON DELETE CASCADE
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_saved_work_products_user ON lawyer_saved_work_products(user_id, created_at DESC)")
        c.commit()


def list_work_products(uid: int, *, limit: int = 40, query: str = "", saved_only: bool = False) -> List[Dict[str, Any]]:
    """Return metadata/excerpts for this lawyer's AI exchanges and draft versions."""
    init_drafting_artifact_tables()
    init_case_ai_history_table()
    init_work_product_bookmarks()
    uid = int(uid)
    limit = max(1, min(int(limit), 80))
    query = str(query or "").strip()[:120]
    like = f"%{query}%"
    with conn() as c:
        rows = c.execute("""SELECT p.*, CASE WHEN s.item_id IS NOT NULL THEN 1 ELSE 0 END AS saved FROM (
            SELECT 'draft' AS item_type, d.id AS item_id, d.case_id, c.file_name AS case_name,
                   d.brief_type AS title, d.status, d.draft_text AS body, d.version_no,
                   d.created_at, d.updated_at
            FROM drafting_artifacts d JOIN cases c ON c.id=d.case_id AND c.user_id=d.user_id
            WHERE d.user_id=? AND c.status!='archived'
            UNION ALL
            SELECT 'ai' AS item_type, CAST(h.id AS TEXT) AS item_id, h.case_id, c.file_name AS case_name,
                   h.question AS title, h.context_mode AS status, h.answer AS body, NULL AS version_no,
                   h.created_at, h.created_at AS updated_at
            FROM case_ai_history h JOIN cases c ON c.id=h.case_id AND c.user_id=h.user_id
            WHERE h.user_id=? AND c.status!='archived'
        ) p LEFT JOIN lawyer_saved_work_products s
          ON s.user_id=? AND s.item_type=p.item_type AND s.item_id=p.item_id
        WHERE (?=0 OR s.item_id IS NOT NULL)
          AND (?='' OR p.title LIKE ? OR p.body LIKE ? OR p.case_name LIKE ?)
        ORDER BY p.updated_at DESC, p.item_id DESC LIMIT ?""",
            (uid, uid, uid, 1 if saved_only else 0, query, like, like, like, limit)).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        body = str(item.pop("body", "") or "")
        item["excerpt"] = body[:280] + ("…" if len(body) > 280 else "")
        item["saved"] = bool(item.get("saved"))
        items.append(item)
    return items


def _work_product_is_saved(uid: int, item_type: str, item_id: str) -> bool:
    with conn() as c:
        return bool(c.execute("SELECT 1 FROM lawyer_saved_work_products WHERE user_id=? AND item_type=? AND item_id=?",
                              (int(uid), str(item_type), str(item_id))).fetchone())


def set_work_product_saved(uid: int, item_type: str, item_id: str, saved: bool) -> bool:
    """Bookmark an owned, non-archived draft or AI exchange."""
    init_drafting_artifact_tables()
    init_case_ai_history_table()
    init_work_product_bookmarks()
    uid = int(uid)
    item_type = str(item_type or "").strip().lower()
    item_id = str(item_id or "").strip()[:80]
    if item_type == "draft":
        with conn() as c:
            row = c.execute("SELECT case_id FROM drafting_artifacts d JOIN cases c ON c.id=d.case_id AND c.user_id=d.user_id WHERE d.id=? AND d.user_id=? AND c.status!='archived'", (item_id, uid)).fetchone()
    elif item_type == "ai" and item_id.isdigit():
        with conn() as c:
            row = c.execute("SELECT h.case_id FROM case_ai_history h JOIN cases c ON c.id=h.case_id AND c.user_id=h.user_id WHERE h.id=? AND h.user_id=? AND c.status!='archived'", (int(item_id), uid)).fetchone()
    else:
        return False
    if not row:
        return False
    with conn() as c:
        if saved:
            c.execute("INSERT OR IGNORE INTO lawyer_saved_work_products(user_id,case_id,item_type,item_id,created_at) VALUES(?,?,?,?,?)",
                      (uid, int(row["case_id"]), item_type, item_id, now_iso()))
        else:
            c.execute("DELETE FROM lawyer_saved_work_products WHERE user_id=? AND item_type=? AND item_id=?", (uid, item_type, item_id))
        c.commit()
    return True
