"""Document persistence boundary."""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from .. import db

class DocumentRepository:
    def list(self, user_id: int, case_id: int) -> List[Dict[str, Any]]:
        with db.conn() as c:
            rows = c.execute("SELECT d.* FROM case_documents d JOIN cases c ON c.id=d.case_id WHERE c.id=? AND c.user_id=? ORDER BY d.id ASC", (int(case_id), int(user_id))).fetchall()
            return [dict(r) for r in rows]

    def add(self, case_id: int, file_name: str, page_count: int = 0,
            extracted_text: str = "") -> Optional[int]:
        with db.conn() as c:
            if not c.execute("SELECT 1 FROM cases WHERE id=? AND status!='archived'", (int(case_id),)).fetchone():
                return None
            cur = c.execute("INSERT INTO case_documents(case_id,file_name,page_count,extracted_text,created_at) VALUES(?,?,?,?,?)", (int(case_id), file_name, int(page_count or 0), extracted_text or "", db.now_iso()))
            c.commit()
            return cur.lastrowid

    def set_storage(self, document_id: int, user_id: int, storage_path: str,
                    file_size: int = 0, sha256: str = "", mime_type: str = "",
                    stored_at: Optional[str] = None) -> bool:
        with db.conn() as c:
            cur = c.execute("""UPDATE case_documents SET storage_path=?,file_size=?,sha256=?,mime_type=?,stored_at=?
                WHERE id=? AND EXISTS (SELECT 1 FROM cases WHERE cases.id=case_documents.case_id AND cases.user_id=? AND cases.status!='archived')""",
                (str(storage_path), int(file_size or 0), str(sha256 or ""), str(mime_type or ""), stored_at or db.now_iso(), int(document_id), int(user_id)))
            c.commit()
            return cur.rowcount == 1

    def delete(self, user_id: int, case_id: int, document_id: int) -> bool:
        # Ownership is checked through the case relation before mutation.
        docs = self.list(user_id, case_id)
        if not any(int(d.get("id")) == int(document_id) for d in docs):
            return False
        with db.conn() as c:
            cur = c.execute(
                "DELETE FROM case_documents WHERE id=? AND case_id=?",
                (int(document_id), int(case_id)),
            )
            c.commit()
            return cur.rowcount == 1
