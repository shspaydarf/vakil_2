"""Case intake workflow shared by Telegram and the future Mini App/API."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from .. import db
from ..calendar_dates import extract_important_dates
from .cases import CaseService
from .documents import DocumentService
from .credits import CreditService


class CaseWorkflowError(RuntimeError):
    """Raised when case intake cannot be completed."""


class CaseIntakeService:
    """Orchestrates quota, case creation, document ingestion and completion.

    UI layers should not reproduce this transaction-like workflow. The existing
    DB functions remain underneath for now; this service is the first canonical
    application-level entry point.
    """

    def __init__(self, cases: Optional[CaseService] = None,
                 documents: Optional[DocumentService] = None,
                 credits: Optional[CreditService] = None):
        self.cases = cases or CaseService()
        self.documents = documents or DocumentService()
        self.credits = credits or CreditService()

    def ingest_one(self, user_id: int, case_name: str, source_path: str | Path,
                   original_name: str, suffix: Optional[str] = None,
                   extract_dates: bool = True) -> Dict[str, Any]:
        uid = int(user_id)
        reservation = None
        case = None
        path = Path(source_path)
        try:
            ok, reservation = self.credits.reserve_case(uid)
            if not ok:
                raise CaseWorkflowError(str(reservation or "سهمیه پرونده کافی نیست."))

            case = self.cases.create(uid, case_name)
            result = self.documents.ingest_file(uid, case["id"], path, original_name, suffix)

            dates = []
            if extract_dates and result.get("text_chars", 0) > 0:
                dates = extract_important_dates(
                    self.cases.text(uid, case["id"]), 40
                )
                if dates:
                    db.add_case_important_dates(uid, case["id"], dates)

            db.finish_case(case["id"], json.dumps({
                "extraction": result.get("diagnostics") or {},
                "document_id": result["document_id"],
                "important_dates": len(dates),
            }, ensure_ascii=False))

            if not self.credits.commit(uid, reservation):
                raise CaseWorkflowError("ثبت نهایی سهمیه پرونده انجام نشد.")

            final_case = self.cases.get(uid, case["id"])
            return {
                "case": final_case,
                "document": result,
                "important_dates": dates,
                "reservation": reservation,
            }
        except Exception as exc:
            if case:
                try:
                    db.fail_case(case["id"], f"{type(exc).__name__}: {exc}")
                except Exception:
                    pass
            if reservation:
                try:
                    self.credits.refund_case(uid, reservation)
                except Exception:
                    pass
            if isinstance(exc, CaseWorkflowError):
                raise
            raise CaseWorkflowError(str(exc) or "پردازش پرونده انجام نشد.") from exc
        finally:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass
