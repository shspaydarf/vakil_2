# -*- coding: utf-8 -*-
"""Phase 8.3: record a bounded runtime download attempt without weakening safeguards."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

@dataclass(frozen=True)
class DownloadTrial:
    source_role: str
    source_url: str
    outcome: str
    detail: str
    attempted_at: str
    downloaded: bool = False
    staged: bool = False
    ocr_run: bool = False
    active_bank_modified: bool = False


def build_download_trial(*, outcome: str, detail: str, source_url: str,
                         attempted_at: str | None = None) -> dict[str, Any]:
    item = DownloadTrial(
        source_role="secondary_reference_only", source_url=source_url,
        outcome=outcome, detail=detail,
        attempted_at=attempted_at or datetime.now(timezone.utc).isoformat(),
    )
    report: dict[str, Any] = {
        "phase": "8.3", "purpose": "single_pdf_download_trial",
        "evidence": asdict(item),
        "constraints": {
            "no_dns_bypass": True, "no_challenge_bypass": True,
            "secondary_source_not_primary": True,
            "active_bank_import_performed": False,
        },
    }
    canonical = json.dumps(report, ensure_ascii=False, sort_keys=True).encode("utf-8")
    report["report_sha256"] = sha256(canonical).hexdigest()
    return report


def validate_download_trial(report: dict[str, Any]) -> bool:
    if report.get("phase") != "8.3" or report.get("purpose") != "single_pdf_download_trial":
        return False
    ev = report.get("evidence", {})
    if ev.get("source_role") != "secondary_reference_only":
        return False
    if any(ev.get(k) is not False for k in ("downloaded", "staged", "ocr_run", "active_bank_modified")):
        return False
    constraints = report.get("constraints", {})
    if not all(constraints.get(k) is True for k in (
        "no_dns_bypass", "no_challenge_bypass", "secondary_source_not_primary")):
        return False
    if constraints.get("active_bank_import_performed") is not False:
        return False
    digest = report.get("report_sha256")
    payload = dict(report); payload.pop("report_sha256", None)
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return digest == sha256(canonical).hexdigest()


def write_trial_report(report: dict[str, Any], path: str | Path) -> Path:
    if not validate_download_trial(report):
        raise ValueError("گزارش آزمایش دریافت معتبر نیست")
    target = Path(path); target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target
