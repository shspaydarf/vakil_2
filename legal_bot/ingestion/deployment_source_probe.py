# -*- coding: utf-8 -*-
"""Phase 10.4.3: bounded Dotic robots/page probe for the deployment runtime.

Only reads robots.txt and one public HTML record page. No assets/PDFs are
downloaded, no candidate is stored, and no legal bank or scheduler is touched.
"""
from __future__ import annotations
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from .live_probe import probe_source
from .policy import ConnectorPolicy

DotiC_SOURCE = {
    "source_id": "national_regulations",
    "name": "سامانه ملی قوانین و مقررات کشور",
    "base_url": "https://dotic.ir/",
    "allowed_hosts": ["dotic.ir", "www.dotic.ir"],
    "pilot_url": "https://dotic.ir/news/21843",
}

def build_report(*, reader=None) -> dict:
    policy = ConnectorPolicy(max_pages=1, max_candidates=0, request_timeout_seconds=8,
        min_request_interval_seconds=3.0, max_asset_bytes=0, allow_downloads=False,
        respect_robots_txt=True, stop_on_403=True, stop_on_429=True,
        stop_on_browser_challenge=True)
    kwargs = {"policy": policy}
    if reader is not None:
        kwargs["reader"] = reader
    result = probe_source(DotiC_SOURCE, **kwargs).to_dict()
    robots_ok = result["robots_status"] in {"read", "not_found"}
    page_ok = result["page_status"] == "ok"
    return {
        "phase": "10.4.3",
        "probe_kind": "dotic_robots_and_single_html_page_only",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runtime": {"hostname": os.getenv("HOSTNAME", "unknown"), "container_hint": os.path.exists("/.dockerenv")},
        "source": result,
        "policy": {"max_html_pages": 1, "pdf_or_asset_downloads": 0,
            "candidate_storage": False, "active_bank_write": False,
            "scheduler_enabled": False, "challenge_bypass": False,
            "only_https_same_host_redirects": True},
        "decision": "page_probe_ok_manual_source_review_required" if robots_ok and page_ok else "no_go_source_access_unverified_or_blocked",
        "legal_authority_confirmed": False,
        "decision_note": "A successful page probe proves only technical public-page access; it does not verify official document authenticity, legal authority, or permission to download linked assets."
    }

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Bounded read-only Dotic source probe")
    parser.add_argument("--output", default="/data/ingestion_diagnostics/phase10_4_3_dotic_probe.json")
    args = parser.parse_args(argv)
    report = build_report()
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    output = Path(args.output)
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
        print(f"Report saved: {output}")
    except OSError as exc:
        print(f"Report file unavailable ({exc}); report follows on stdout:")
    print(rendered)
    return 0 if report["decision"] == "page_probe_ok_manual_source_review_required" else 2

if __name__ == "__main__":
    raise SystemExit(main())
