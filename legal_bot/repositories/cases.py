"""Case persistence boundary.

The repository owns persistence concerns only. Business rules remain in
CaseService; this module deliberately delegates to the proven legacy db layer
while we migrate its SQL incrementally.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
from .. import db

class CaseRepository:
    def get(self, user_id: int, case_id: int) -> Optional[Dict[str, Any]]:
        with db.conn() as c:
            row = c.execute("SELECT * FROM cases WHERE id=? AND user_id=?", (int(case_id), int(user_id))).fetchone()
            return dict(row) if row else None

    def list(self, user_id: int, limit: int = 20, query: str = "", include_archived: bool = False) -> List[Dict[str, Any]]:
        with db.conn() as c:
            clauses = ["c.user_id=?"]
            params: list[Any] = [int(user_id)]
            if not include_archived:
                clauses.append("c.status!='archived'")
            query = (query or "").strip()[:120]
            if query:
                clauses.append("LOWER(COALESCE(c.file_name,'')) LIKE LOWER(?)")
                params.append(f"%{query}%")
            params.append(int(limit))
            rows = c.execute(f"""SELECT c.*,
                (SELECT COUNT(*) FROM cases c2 WHERE c2.user_id=c.user_id AND c2.id<=c.id) AS case_number
                FROM cases c WHERE {' AND '.join(clauses)} ORDER BY c.id DESC LIMIT ?""", tuple(params)).fetchall()
            return [dict(r) for r in rows]

    def create(self, user_id: int, name: str, *, stage: str = "new", priority: str = "normal", next_action: str = "") -> int:
        with db.conn() as c:
            now = db.now_iso()
            cur = c.execute(
                "INSERT INTO cases(user_id,file_name,status,stage,priority,next_action,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (int(user_id), name, "processing", stage, priority, next_action, now, now),
            )
            c.commit()
            return cur.lastrowid

    def set_active(self, user_id: int, case_id: Optional[int]) -> bool:
        with db.conn() as c:
            if case_id is not None:
                row = c.execute("SELECT 1 FROM cases WHERE id=? AND user_id=?", (int(case_id), int(user_id))).fetchone()
                if not row:
                    return False
            cur = c.execute("UPDATE users SET active_case_id=? WHERE user_id=?", (case_id, int(user_id)))
            c.commit()
            return cur.rowcount == 1

    def active_id(self, user_id: int) -> Optional[int]:
        with db.conn() as c:
            row = c.execute("SELECT active_case_id FROM users WHERE user_id=?", (int(user_id),)).fetchone()
            return int(row[0]) if row and row[0] is not None else None

    def clear_active(self, user_id: int) -> bool:
        with db.conn() as c:
            cur = c.execute("UPDATE users SET active_case_id=NULL WHERE user_id=?", (int(user_id),))
            c.commit()
            return cur.rowcount == 1

    def update_metadata(self, user_id: int, case_id: int, *, name: str, stage: str, priority: str, next_action: str) -> bool:
        with db.conn() as c:
            row = c.execute("SELECT status FROM cases WHERE id=? AND user_id=?", (int(case_id), int(user_id))).fetchone()
            if not row or row[0] == "archived":
                return False
            cur = c.execute(
                "UPDATE cases SET file_name=?, stage=?, priority=?, next_action=?, updated_at=? WHERE id=? AND user_id=?",
                (name, stage, priority, next_action, db.now_iso(), int(case_id), int(user_id)),
            )
            c.commit()
            return cur.rowcount == 1

    def archive(self, user_id: int, case_id: int) -> bool:
        with db.conn() as c:
            row = c.execute("SELECT status FROM cases WHERE id=? AND user_id=?", (int(case_id), int(user_id))).fetchone()
            if not row or row[0] in {"archived", "processing"}:
                return False
            source = row[0] if row[0] in {"completed", "failed"} else "completed"
            cur = c.execute(
                "UPDATE cases SET status='archived', archived_at=?, archived_from_status=? WHERE id=? AND user_id=? AND status!='archived'",
                (db.now_iso(), source, int(case_id), int(user_id)),
            )
            c.execute("UPDATE users SET active_case_id=NULL WHERE user_id=? AND active_case_id=?", (int(user_id), int(case_id)))
            c.commit()
            return cur.rowcount == 1

    def restore(self, user_id: int, case_id: int) -> bool:
        with db.conn() as c:
            row = c.execute("SELECT archived_from_status FROM cases WHERE id=? AND user_id=? AND status='archived'", (int(case_id), int(user_id))).fetchone()
            if not row:
                return False
            source = row[0] if row[0] in {"completed", "failed"} else "completed"
            cur = c.execute("UPDATE cases SET status=?, archived_at=NULL, archived_from_status=NULL WHERE id=? AND user_id=? AND status='archived'", (source, int(case_id), int(user_id)))
            c.commit()
            return cur.rowcount == 1

    def delete(self, user_id: int, case_id: int) -> bool:
        return db.delete_case(user_id, case_id)

    def documents(self, user_id: int, case_id: int) -> List[Dict[str, Any]]:
        with db.conn() as c:
            rows = c.execute("SELECT d.* FROM case_documents d JOIN cases c ON c.id=d.case_id WHERE c.id=? AND c.user_id=? ORDER BY d.id ASC", (int(case_id), int(user_id))).fetchall()
            return [dict(r) for r in rows]

    def text(self, user_id: int, case_id: int) -> str:
        docs = self.documents(user_id, case_id)
        chunks = []
        for d in docs:
            text = (d.get("extracted_text") or "").strip()
            if not text:
                continue
            chunks.append(text)
        return "\n\n".join(chunks).strip()

    def count_versions(self, user_id: int, case_id: int) -> int:
        with db.conn() as c:
            row = c.execute("SELECT COUNT(*) FROM case_versions v JOIN cases c ON c.id=v.case_id WHERE v.case_id=? AND c.user_id=?", (int(case_id), int(user_id))).fetchone()
            return int(row[0] or 0)

    def add_version(self, user_id: int, case_id: int, file_name: str,
                    page_count: int = 0, extracted_text: str = "") -> Tuple[int, int]:
        return db.add_case_version(user_id, case_id, file_name, page_count, extracted_text)

    def versions(self, user_id: int, case_id: int) -> List[Dict[str, Any]]:
        with db.conn() as c:
            rows = c.execute("SELECT v.* FROM case_versions v JOIN cases c ON c.id=v.case_id WHERE v.case_id=? AND c.user_id=? ORDER BY v.version_no ASC", (int(case_id), int(user_id))).fetchall()
            return [dict(r) for r in rows]

    def note(self, user_id: int, case_id: int) -> Optional[Dict[str, Any]]:
        with db.conn() as c:
            row = c.execute("SELECT n.* FROM case_lawyer_notes n JOIN cases c ON c.id=n.case_id WHERE n.case_id=? AND c.user_id=?", (int(case_id), int(user_id))).fetchone()
            return dict(row) if row else None

    def save_note(self, user_id: int, case_id: int, text: str) -> bool:
        with db.conn() as c:
            case = c.execute("SELECT status FROM cases WHERE id=? AND user_id=?", (int(case_id), int(user_id))).fetchone()
            if not case or case[0] == "archived":
                return False
            c.execute("INSERT INTO case_lawyer_notes(case_id,user_id,note_text,updated_at) VALUES(?,?,?,?) ON CONFLICT(case_id) DO UPDATE SET note_text=excluded.note_text,user_id=excluded.user_id,updated_at=excluded.updated_at", (int(case_id), int(user_id), text, db.now_iso()))
            c.commit()
            return True

    def clear_note(self, user_id: int, case_id: int) -> bool:
        with db.conn() as c:
            cur = c.execute("DELETE FROM case_lawyer_notes WHERE case_id=? AND user_id=?", (int(case_id), int(user_id)))
            c.commit()
            return cur.rowcount > 0
