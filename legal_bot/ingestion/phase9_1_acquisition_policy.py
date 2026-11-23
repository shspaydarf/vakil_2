# -*- coding: utf-8 -*-
"""Phase 9.1: simple, source-aware acquisition routing policy.

This module plans routes only. It performs no network access, downloads, browser
automation, OCR, staging writes, or active-bank mutations.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Any
from urllib.parse import urlparse

SOURCE_ALLOWED_HOSTS = {
    "majles_rc": {"rc.majlis.ir"},
    # Both canonical and non-www hosts are accepted by the read-only connector.
    "ekhtebar": {"www.ekhtebar.ir", "ekhtebar.ir"},
}

@dataclass(frozen=True)
class AcquisitionRoute:
    source_id: str
    source_role: str
    source_url: str
    route: str
    output_class: str
    requires_human_review: bool = True


def build_acquisition_plan(source_id: str, source_url: str, *, direct_pdf_observed: bool = False) -> dict[str, Any]:
    parsed = urlparse(source_url)
    allowed_hosts = SOURCE_ALLOWED_HOSTS.get(source_id)
    if not allowed_hosts:
        raise ValueError("شناسه منبع ناشناخته است")
    if (parsed.scheme != "https" or (parsed.hostname or "").lower() not in allowed_hosts
            or parsed.username or parsed.password or parsed.port not in (None, 443)):
        raise ValueError("منبع باید HTTPS و میزبان دقیق آن در allowlist همان منبع باشد")
    if source_id == "majles_rc":
        role = "official_primary_candidate"
        # The three-step print workflow is deliberately deferred; HTML is the
        # low-complexity fallback and a browser-generated PDF is derivative.
        route = "direct_pdf_if_observed" if direct_pdf_observed else "official_html_capture_candidate"
        output = "official_pdf" if direct_pdf_observed else "html_snapshot_not_pdf"
    elif source_id == "ekhtebar":
        role = "secondary_reference_only"
        route = "direct_pdf_if_observed" if direct_pdf_observed else "listing_and_link_discovery_candidate"
        output = "secondary_pdf_quarantine_only" if direct_pdf_observed else "metadata_candidate_only"
    else:
        raise ValueError("شناسه منبع ناشناخته است")
    route_item = AcquisitionRoute(source_id, role, source_url, route, output)
    plan: dict[str, Any] = {
        "phase": "9.1", "purpose": "low_complexity_acquisition_routing",
        "route": asdict(route_item),
        "safety": {
            "network_access_performed": False, "download_performed": False,
            "browser_automation_enabled": False, "print_workflow_automation_enabled": False,
            "ocr_performed": False, "staging_written": False,
            "active_bank_modified": False, "legal_validity_assessed": False,
            "secondary_source_can_replace_primary": False,
        },
        "notes": [
            "PDF تولیدشده از HTML، نسخه مشتق‌شده است و PDF اصلی محسوب نمی‌شود.",
            "اختبار فقط منبع ثانویه است و خروجی آن صرفاً برای قرنطینه و تطبیق انسانی مجاز است.",
            "مسیر چندمرحله‌ای چاپ مجلس فعلاً خودکارسازی نمی‌شود.",
        ],
    }
    canonical = json.dumps(plan, ensure_ascii=False, sort_keys=True).encode("utf-8")
    plan["plan_sha256"] = sha256(canonical).hexdigest()
    return plan


def validate_acquisition_plan(plan: dict[str, Any]) -> bool:
    if plan.get("phase") != "9.1" or plan.get("purpose") != "low_complexity_acquisition_routing":
        return False
    route = plan.get("route", {})
    source_id = route.get("source_id")
    allowed_hosts = SOURCE_ALLOWED_HOSTS.get(source_id)
    if not allowed_hosts:
        return False
    if route.get("source_role") == "secondary_reference_only" and route.get("output_class") == "official_pdf":
        return False
    if source_id == "ekhtebar" and route.get("source_role") != "secondary_reference_only":
        return False
    if source_id == "majles_rc" and route.get("source_role") != "official_primary_candidate":
        return False
    safety = plan.get("safety", {})
    required_false = ("network_access_performed", "download_performed", "browser_automation_enabled",
                      "print_workflow_automation_enabled", "ocr_performed", "staging_written",
                      "active_bank_modified", "legal_validity_assessed", "secondary_source_can_replace_primary")
    if any(safety.get(key) is not False for key in required_false):
        return False
    try:
        parsed = urlparse(route.get("source_url", ""))
        if (parsed.scheme != "https" or (parsed.hostname or "").lower() not in allowed_hosts
                or parsed.username or parsed.password or parsed.port not in (None, 443)):
            return False
    except (TypeError, ValueError):
        return False
    digest = plan.get("plan_sha256")
    payload = dict(plan); payload.pop("plan_sha256", None)
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return digest == sha256(canonical).hexdigest()
