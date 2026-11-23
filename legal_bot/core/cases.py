"""Case application service.

This module is intentionally UI-agnostic. Telegram handlers, the future HTTP
API, and the Mini App should all call this layer instead of implementing case
rules themselves.

The first migration step delegates persistence to the existing db.py. This is
an anti-corruption layer: we can move the underlying repository later without
changing the public service contract.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .. import db
from ..repositories import CaseRepository
from ..config import CASE_NAME_MAX_CHARS, MAX_CASE_NOTE_CHARS, MAX_CASE_VERSIONS

CASE_STAGES = {"new", "intake", "research", "review", "drafting", "closed"}
CASE_PRIORITIES = {"low", "normal", "high", "urgent"}


class CaseValidationError(ValueError):
    """Raised when a case command is invalid for the current business rules."""


def _uid(value: Any) -> int:
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise CaseValidationError("شناسه کاربر نامعتبر است.")
    if value <= 0:
        raise CaseValidationError("شناسه کاربر نامعتبر است.")
    return value


def _cid(value: Any) -> int:
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise CaseValidationError("شناسه پرونده نامعتبر است.")
    if value <= 0:
        raise CaseValidationError("شناسه پرونده نامعتبر است.")
    return value


class CaseService:
    def __init__(self, repository: CaseRepository | None = None):
        self.repository = repository or CaseRepository()

    """Business-facing case operations.

    Contract goals:
      * every operation is user-scoped;
      * UI does not need to know SQL or legacy db function names;
      * archived/processing rules live here, not in Telegram callbacks;
      * return values are JSON-friendly dictionaries/lists for the future API.
    """

    def get(self, user_id: int, case_id: int) -> Optional[Dict[str, Any]]:
        return self.repository.get(_uid(user_id), _cid(case_id))

    def list(self, user_id: int, limit: int = 20, query: str = "", include_archived: bool = False) -> List[Dict[str, Any]]:
        uid = _uid(user_id)
        limit = max(1, min(int(limit), 100))
        return self.repository.list(uid, limit, query=query, include_archived=include_archived)

    def update(self, user_id: int, case_id: int, *, name: str | None = None, stage: str | None = None,
               priority: str | None = None, next_action: str | None = None) -> Dict[str, Any]:
        uid, cid = _uid(user_id), _cid(case_id)
        current = self.repository.get(uid, cid)
        if not current:
            raise CaseValidationError("پرونده پیدا نشد.")
        if current.get("status") == "archived":
            raise CaseValidationError("پرونده بایگانی‌شده قابل ویرایش نیست.")
        final_name = current.get("file_name") or "" if name is None else str(name).strip()
        if not final_name:
            raise CaseValidationError("نام پرونده الزامی است.")
        if len(final_name) > CASE_NAME_MAX_CHARS:
            raise CaseValidationError(f"نام پرونده نباید بیشتر از {CASE_NAME_MAX_CHARS} کاراکتر باشد.")
        final_stage = str(current.get("stage") or "new") if stage is None else str(stage).strip().lower()
        final_priority = str(current.get("priority") or "normal") if priority is None else str(priority).strip().lower()
        final_next = str(current.get("next_action") or "") if next_action is None else str(next_action).strip()[:1000]
        if final_stage not in CASE_STAGES:
            raise CaseValidationError("مرحله پرونده نامعتبر است.")
        if final_priority not in CASE_PRIORITIES:
            raise CaseValidationError("اولویت پرونده نامعتبر است.")
        if not self.repository.update_metadata(uid, cid, name=final_name, stage=final_stage, priority=final_priority, next_action=final_next):
            raise RuntimeError("به‌روزرسانی پرونده انجام نشد.")
        case = self.repository.get(uid, cid)
        if not case:
            raise RuntimeError("پرونده پس از به‌روزرسانی قابل بازیابی نیست.")
        return case

    def create(self, user_id: int, name: str, *, stage: str = "new", priority: str = "normal", next_action: str = "") -> Dict[str, Any]:
        uid = _uid(user_id)
        name = (name or "").strip()
        if not name:
            raise CaseValidationError("نام پرونده الزامی است.")
        if len(name) > CASE_NAME_MAX_CHARS:
            raise CaseValidationError(f"نام پرونده نباید بیشتر از {CASE_NAME_MAX_CHARS} کاراکتر باشد.")
        stage = str(stage or "new").strip().lower()
        priority = str(priority or "normal").strip().lower()
        next_action = str(next_action or "").strip()[:1000]
        if stage not in CASE_STAGES:
            raise CaseValidationError("مرحله پرونده نامعتبر است.")
        if priority not in CASE_PRIORITIES:
            raise CaseValidationError("اولویت پرونده نامعتبر است.")
        if not db.get_user(uid):
            raise CaseValidationError("کاربر پیدا نشد.")
        case_id = self.repository.create(uid, name, stage=stage, priority=priority, next_action=next_action)
        if not case_id:
            raise RuntimeError("ایجاد پرونده انجام نشد.")
        self.repository.set_active(uid, case_id)
        case = self.repository.get(uid, case_id)
        if not case:
            raise RuntimeError("پرونده پس از ایجاد قابل بازیابی نیست.")
        return case

    def create_empty(self, user_id: int, name: str, *, stage: str = "new", priority: str = "normal", next_action: str = "") -> Dict[str, Any]:
        """Create a ready-to-use empty case shell.

        Intake with a document remains processing until ingestion finishes;
        an API-created empty shell has no pending work, so it must not be left
        in ``processing`` where archive/restore rules treat it as unfinished.
        """
        case = self.create(user_id, name, stage=stage, priority=priority, next_action=next_action)
        db.finish_case(case["id"], "{}")
        final = self.get(user_id, case["id"])
        if not final:
            raise RuntimeError("پرونده پس از ایجاد قابل بازیابی نیست.")
        return final

    def set_active(self, user_id: int, case_id: Optional[int]) -> bool:
        uid = _uid(user_id)
        if case_id is None:
            return self.repository.clear_active(uid)
        cid = _cid(case_id)
        case = self.repository.get(uid, cid)
        if not case:
            return False
        if case.get("status") == "archived":
            return False
        return self.repository.set_active(uid, cid)

    def active(self, user_id: int) -> Optional[Dict[str, Any]]:
        uid = _uid(user_id)
        cid = self.repository.active_id(uid)
        if cid is None:
            return None
        case = self.repository.get(uid, cid)
        if not case or case.get("status") == "archived":
            # Repair stale active_case_id rather than exposing it to clients.
            self.repository.clear_active(uid)
            return None
        return case

    def archive(self, user_id: int, case_id: int) -> bool:
        uid, cid = _uid(user_id), _cid(case_id)
        case = self.repository.get(uid, cid)
        if not case or case.get("status") in {"archived", "processing"}:
            return False
        return self.repository.archive(uid, cid)

    def restore(self, user_id: int, case_id: int) -> bool:
        return self.repository.restore(_uid(user_id), _cid(case_id))

    def delete(self, user_id: int, case_id: int) -> bool:
        return self.repository.delete(_uid(user_id), _cid(case_id))

    def documents(self, user_id: int, case_id: int) -> List[Dict[str, Any]]:
        uid, cid = _uid(user_id), _cid(case_id)
        if not self.repository.get(uid, cid):
            return []
        return self.repository.documents(uid, cid)

    def text(self, user_id: int, case_id: int) -> str:
        return self.repository.text(_uid(user_id), _cid(case_id))

    def add_version(self, user_id: int, case_id: int, file_name: str, page_count: int = 0,
                    extracted_text: str = "") -> Tuple[int, int]:
        uid, cid = _uid(user_id), _cid(case_id)
        case = self.repository.get(uid, cid)
        if not case:
            raise CaseValidationError("پرونده پیدا نشد.")
        if case.get("status") == "archived":
            raise CaseValidationError("پرونده بایگانی‌شده قابل ویرایش نیست.")
        if MAX_CASE_VERSIONS and self.repository.count_versions(uid, cid) >= MAX_CASE_VERSIONS:
            raise CaseValidationError("حداکثر تعداد نسخه‌های این پرونده تکمیل شده است.")
        result = self.repository.add_version(uid, cid, (file_name or "").strip(), int(page_count or 0), extracted_text or "")
        if not result or result[0] is None:
            raise RuntimeError("افزودن نسخه پرونده انجام نشد.")
        return result

    def versions(self, user_id: int, case_id: int) -> List[Dict[str, Any]]:
        return self.repository.versions(_uid(user_id), _cid(case_id))

    def note(self, user_id: int, case_id: int) -> Optional[Dict[str, Any]]:
        return self.repository.note(_uid(user_id), _cid(case_id))

    def save_note(self, user_id: int, case_id: int, note_text: str) -> bool:
        uid, cid = _uid(user_id), _cid(case_id)
        note_text = (note_text or "").strip()
        if len(note_text) > MAX_CASE_NOTE_CHARS:
            raise CaseValidationError(f"یادداشت نباید بیشتر از {MAX_CASE_NOTE_CHARS} کاراکتر باشد.")
        case = self.repository.get(uid, cid)
        if not case:
            return False
        if case.get("status") == "archived":
            return False
        return self.repository.save_note(uid, cid, note_text)

    def clear_note(self, user_id: int, case_id: int) -> bool:
        return self.repository.clear_note(_uid(user_id), _cid(case_id))
