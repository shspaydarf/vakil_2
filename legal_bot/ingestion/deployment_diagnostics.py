# -*- coding: utf-8 -*-
"""Deployment-side, read-only source connectivity diagnostic runner.

Run this inside the actual API container. It checks system DNS and verified TLS
only; it does not issue HTTP requests, download documents, or alter legal data.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .network_diagnostics import diagnose_host

SOURCE_TARGETS = {
    "dotic": {"source_id": "dotic", "url": "https://dotic.ir/", "role": "official_primary"},
    "rrk": {"source_id": "rrk", "url": "https://www.rrk.ir/", "role": "official_primary"},
    "majlis_rc": {"source_id": "majlis_rc", "url": "https://rc.majlis.ir/", "role": "official_primary_candidate"},
    "eadil": {"source_id": "eadil", "url": "https://eadil.com/", "role": "official_primary_candidate"},
    "ekhtebar": {"source_id": "ekhtebar", "url": "https://www.ekhtebar.ir/", "role": "secondary_discovery_only"},
}


def build_report(source_ids: Iterable[str], *, timeout: float = 4.0) -> dict:
    rows = []
    for source_id in source_ids:
        target = SOURCE_TARGETS[source_id]
        result = diagnose_host(target["url"], timeout=timeout).to_dict()
        result.update({"source_id": source_id, "role": target["role"], "url": target["url"]})
        rows.append(result)
    return {
        "phase": "10.4.2",
        "diagnostic_kind": "deployment_dns_tls_only",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runtime": {"hostname": os.getenv("HOSTNAME", "unknown"), "container_hint": os.path.exists("/.dockerenv")},
        "policy": {
            "http_requests_sent": False, "pdf_downloads_attempted": False,
            "robots_checked": False, "active_bank_write": False,
            "scheduler_enabled": False, "alternate_dns_or_bypass": False,
        },
        "sources": rows,
        "decision": "tls_ready_for_next_source_review" if any(r["role"] != "secondary_discovery_only" for r in rows) and all(r["status"] == "tls_ok_http_not_tested" for r in rows if r["role"] != "secondary_discovery_only") else "no_go_live_acquisition",
        "decision_note": "TLS success is only network readiness; it does not authorize crawling, prove robots permission, or establish legal validity.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only MACHINA deployment DNS/TLS diagnostics")
    parser.add_argument("--source", choices=["dotic", "rrk", "majlis_rc", "eadil", "ekhtebar", "all"], default="dotic")
    parser.add_argument("--timeout", type=float, default=4.0)
    parser.add_argument("--output", default="/data/ingestion_diagnostics/phase10_4_2_deployment.json")
    args = parser.parse_args(argv)
    if not 0.5 <= args.timeout <= 10:
        parser.error("--timeout must be between 0.5 and 10 seconds")
    selected = list(SOURCE_TARGETS) if args.source == "all" else [args.source]
    report = build_report(selected, timeout=args.timeout)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    output = Path(args.output)
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
        print(f"Report saved: {output}")
    except OSError as exc:
        print(f"Report file unavailable ({exc}); report follows on stdout:")
    print(rendered)
    return 0 if report["decision"] == "tls_ready_for_next_source_review" else 2


if __name__ == "__main__":
    raise SystemExit(main())
