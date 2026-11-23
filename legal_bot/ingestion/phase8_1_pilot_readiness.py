# -*- coding: utf-8 -*-
"""Phase 8.1: bounded real-source pilot readiness record.

This module records evidence and plans a tiny pilot. It does not fetch pages,
PDFs, bypass challenges, or mutate staging/active legal data.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any
from urllib.parse import urlparse


@dataclass(frozen=True)
class PilotTarget:
    source_id: str
    source_role: str
    record_url: str
    record_id: str
    title: str
    acquisition_route: tuple[str, ...]
    evidence_origin: str
    legal_status: str = "not_assessed"


@dataclass(frozen=True)
class SourceObservation:
    source_id: str
    observed_at: str
    outcome: str
    observed_url: str
    detail: str
    evidence_origin: str


def build_phase8_1_plan() -> dict[str, Any]:
    """Return the single-record pilot plan using the user-supplied Majles URL."""
    target = PilotTarget(
        source_id="majles_rc",
        source_role="official_primary_candidate",
        record_url="https://rc.majlis.ir/fa/law/show/93849",
        record_id="93849",
        title="قانون حمایت از کودکان و نوجوانان",
        acquisition_route=(
            "record_page",
            "user_observed_button: دریافت نسخه چاپی",
            "user_observed_button: چاپ قانون",
            "user_observed_action: دانلود PDF",
        ),
        evidence_origin="user_supplied_url_and_screenshots",
    )
    observations = [
        SourceObservation(
            source_id="majles_rc",
            observed_at="2026-11-01",
            outcome="web_fetch_timeout",
            observed_url=target.record_url,
            detail="صفحه از محیط بررسی وب باز نشد؛ این نتیجه وضعیت اتصال از محیط اجرای MACHINA را مشخص نمی‌کند.",
            evidence_origin="chat_web_open_attempt",
        ),
        SourceObservation(
            source_id="ekhtebar",
            observed_at="2026-11-01",
            outcome="javascript_challenge",
            observed_url="https://www.ekhtebar.ir/قوانین/",
            detail="درخواست به صفحه challenge هدایت شد و فعال‌سازی JavaScript خواسته شد؛ هیچ تلاشی برای عبور از challenge انجام نشد.",
            evidence_origin="chat_web_open_attempt",
        ),
    ]
    payload = {
        "phase": "8.1",
        "plan_type": "single_document_source_route_pilot",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "targets": [asdict(target)],
        "observations": [asdict(item) for item in observations],
        "limits": {
            "network_fetch_performed_by_module": False,
            "pdf_downloaded": False,
            "ocr_performed": False,
            "staging_written": False,
            "active_bank_modified": False,
            "secondary_source_may_replace_official": False,
        },
        "next_gate": "8.2_manual_or_authorized_live_probe_and_pdf_sample",
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    payload["plan_sha256"] = sha256(canonical).hexdigest()
    return payload


def validate_phase8_1_plan(plan: dict[str, Any]) -> bool:
    if plan.get("phase") != "8.1" or plan.get("plan_type") != "single_document_source_route_pilot":
        return False
    targets = plan.get("targets")
    if not isinstance(targets, list) or len(targets) != 1:
        return False
    target = targets[0]
    parsed = urlparse(target.get("record_url", ""))
    if parsed.scheme != "https" or parsed.hostname != "rc.majlis.ir":
        return False
    if target.get("record_id") != "93849" or target.get("source_role") != "official_primary_candidate":
        return False
    limits = plan.get("limits", {})
    required_false = ("network_fetch_performed_by_module", "pdf_downloaded", "ocr_performed", "staging_written", "active_bank_modified")
    if any(limits.get(key) is not False for key in required_false):
        return False
    if limits.get("secondary_source_may_replace_official") is not False:
        return False
    digest = plan.get("plan_sha256")
    unhashed = dict(plan)
    unhashed.pop("plan_sha256", None)
    canonical = json.dumps(unhashed, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return digest == sha256(canonical).hexdigest()
