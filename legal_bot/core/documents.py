"""Document application service.

The service owns the document-ingestion contract used by Telegram today and by
HTTP/Mini App clients later. Transport-specific download code stays outside.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional
import json

from .. import db
from ..repositories import DocumentRepository
from ..files import extract_with_diagnostics
from ..storage import store_case_file, validate_supported_file
from ..config import MAX_CASE_ADDITIONS, MAX_CASE_ADDITION_FILES
from ..calendar_dates import extract_important_dates
from ..document_facts import extract_document_facts


class DocumentValidationError(ValueError):
    """Raised when a document cannot be accepted by the application rules."""


def _uid(value: Any) -> int:
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise DocumentValidationError("شناسه کاربر نامعتبر است.")
    if value <= 0:
        raise DocumentValidationError("شناسه کاربر نامعتبر است.")
    return value


def _cid(value: Any) -> int:
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise DocumentValidationError("شناسه پرونده نامعتبر است.")
    if value <= 0:
        raise DocumentValidationError("شناسه پرونده نامعتبر است.")
    return value


class DocumentService:
    def __init__(self, repository: DocumentRepository | None = None):
        self.repository = repository or DocumentRepository()

    """UI-agnostic document ingestion and retrieval."""

    def list(self, user_id: int, case_id: int):
        uid, cid = _uid(user_id), _cid(case_id)
        if not db.get_case(uid, cid):
            return []
        return self.repository.list(uid, cid)

    def ingest_file(self, user_id: int, case_id: int, source_path: str | Path,
                    original_name: str, suffix: Optional[str] = None) -> Dict[str, Any]:
        """Validate, extract, durably store, and register one case document.

        Persistence is compensating: if DB registration or durable storage fails,
        the newly-created artifact/row is removed where possible.
        """
        uid, cid = _uid(user_id), _cid(case_id)
        case = db.get_case(uid, cid)
        if not case:
            raise DocumentValidationError("پرونده پیدا نشد.")
        if case.get("status") == "archived":
            raise DocumentValidationError("پرونده بایگانی‌شده قابل ویرایش نیست.")

        path = Path(source_path)
        suffix = (suffix or path.suffix or "").lower()
        if not validate_supported_file(path, suffix):
            raise DocumentValidationError("محتوای فایل با پسوند اعلام‌شده سازگار نیست.")

        text, diagnostics = extract_with_diagnostics(path)
        if not (text or "").strip():
            raise DocumentValidationError(
                "از فایل متن قابل استفاده استخراج نشد. "
                + str(diagnostics.get("error") or "")
            )

        stored = None
        doc_id = None
        try:
            stored = store_case_file(cid, path, original_name, "documents")
            doc_id = self.repository.add(
                cid,
                (original_name or path.name).strip() or path.name,
                int(diagnostics.get("pages") or 1),
                text,
            )
            if not doc_id:
                raise RuntimeError("ثبت سند در پایگاه‌داده انجام نشد.")
            if not self.repository.set_storage(
                doc_id, uid, stored["storage_path"], stored["file_size"],
                stored["sha256"], stored["mime_type"]
            ):
                raise RuntimeError("ثبت مسیر پایدار سند در پایگاه‌داده انجام نشد.")
        except Exception:
            if doc_id:
                try:
                    self.delete_registered(uid, cid, doc_id)
                except Exception:
                    pass
            if stored:
                try:
                    Path(stored["absolute_path"]).unlink(missing_ok=True)
                except Exception:
                    pass
            raise

        db.set_active_case(uid, cid)
        return {
            "document_id": int(doc_id),
            "case_id": cid,
            "file_name": (original_name or path.name).strip() or path.name,
            "page_count": int(diagnostics.get("pages") or 1),
            "text_chars": len(text),
            "diagnostics": diagnostics,
            "storage": stored,
        }

    def delete_registered(self, user_id: int, case_id: int, document_id: int) -> bool:
        """Delete the registration and its durable file when present."""
        uid, cid, did = _uid(user_id), _cid(case_id), int(document_id)
        docs = self.repository.list(uid, cid)
        target = next((d for d in docs if int(d.get("id")) == did), None)
        if not target:
            return False
        ok = self.repository.delete(uid, cid, did)
        if ok and target.get("storage_path"):
            from ..config import CASE_STORAGE_DIR
            try:
                root = CASE_STORAGE_DIR.resolve()
                path = (CASE_STORAGE_DIR.parent / str(target["storage_path"])).resolve()
                if path.is_file() and root in path.parents:
                    path.unlink(missing_ok=True)
            except OSError:
                pass
        return ok

    def public_list(self, user_id: int, case_id: int):
        """Return document metadata safe for product/API presentation."""
        docs = self.list(user_id, case_id)
        result = []
        for doc in docs:
            text = (doc.get("extracted_text") or "").strip()
            result.append({
                "id": int(doc.get("id")),
                "case_id": int(doc.get("case_id")),
                "file_name": doc.get("file_name") or "سند بدون نام",
                "page_count": int(doc.get("page_count") or 0),
                "file_size": int(doc.get("file_size") or 0),
                "mime_type": doc.get("mime_type") or "",
                "sha256": doc.get("sha256") or "",
                "created_at": doc.get("created_at"),
                "stored_at": doc.get("stored_at"),
                "text_chars": len(text),
                "preview": text[:700],
                "has_text": bool(text),
                # Candidate facts are source-linked and explicitly unverified.
                # Keep the raw extracted text out of the public contract.
                "extracted_facts": extract_document_facts(text, limit=40),
                "facts_need_review": True if text else False,
            })
        return result

    def add_files(self, user_id: int, case_id: int, files) -> Dict[str, Any]:
        """Ingest one Mini App upload action, including a small multi-file batch.

        The first upload completes an empty/processing case. Later uploads are
        treated as one evidence-addition session, matching the Telegram flow.
        """
        uid, cid = _uid(user_id), _cid(case_id)
        case = db.get_case(uid, cid)
        if not case:
            raise DocumentValidationError("پرونده پیدا نشد.")
        if case.get("status") == "archived":
            raise DocumentValidationError("پرونده بایگانی‌شده قابل ویرایش نیست.")
        items = list(files or [])
        if not items:
            raise DocumentValidationError("حداقل یک فایل لازم است.")
        if len(items) > MAX_CASE_ADDITION_FILES:
            raise DocumentValidationError(f"در هر نوبت حداکثر {MAX_CASE_ADDITION_FILES} فایل قابل افزودن است.")

        existing_docs = self.list(uid, cid)
        is_first_upload = not existing_docs
        addition_no = None
        if not is_first_upload:
            if MAX_CASE_ADDITIONS <= 0 or db.count_case_additions(uid, cid) >= MAX_CASE_ADDITIONS:
                raise DocumentValidationError(f"سقف افزودن‌های این پرونده ({MAX_CASE_ADDITIONS} نوبت) پر شده است.")
            started = db.start_case_addition(uid, cid)
            if not started:
                raise DocumentValidationError("نوبت افزودن سند شروع نشد.")
            addition_no = int(started[1])

        results = []
        try:
            for item in items:
                if isinstance(item, dict):
                    source_path = item.get("path")
                    original_name = item.get("name") or Path(source_path).name
                    suffix = item.get("suffix")
                else:
                    source_path, original_name, suffix = item
                results.append(self.ingest_file(uid, cid, source_path, original_name, suffix))
                if addition_no is not None and not db.increment_case_addition_files(uid, cid, addition_no):
                    raise RuntimeError("ثبت تعداد فایل‌های نوبت افزودن انجام نشد.")

            text = db.get_case_text(uid, cid) or ""
            dates = extract_important_dates(text, 40) if text.strip() else []
            if dates:
                db.add_case_important_dates(uid, cid, dates)

            if is_first_upload:
                db.finish_case(cid, json.dumps({
                    "document_id": results[0]["document_id"],
                    "documents_added": len(results),
                    "important_dates": len(dates),
                }, ensure_ascii=False))
            db.set_active_case(uid, cid)
            final_case = db.get_case(uid, cid)
            return {
                "case": final_case,
                "documents": results,
                "document_count": len(self.list(uid, cid)),
                "important_dates": dates,
                "addition_no": addition_no,
            }
        except Exception:
            # A Mini App upload is one user action, so the batch must be atomic:
            # do not leave half an addition behind when one file fails.
            for result in reversed(results):
                try:
                    self.delete_registered(uid, cid, result["document_id"])
                except Exception:
                    pass
            if addition_no is not None:
                try:
                    db.delete_case_addition(uid, cid, addition_no)
                except Exception:
                    pass
            raise
