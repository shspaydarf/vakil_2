# -*- coding: utf-8 -*-
"""Phase 10.4.6: controlled single-document Dotic pilot intake.

This runner deliberately does not fetch from the network. It accepts one PDF
already obtained by an operator through an authorized route, checks the prior
source-readiness reports, validates the bytes, and stores the original plus
manifest in an isolated quarantine directory. It never writes active JSON banks.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from .dotic_pdf_validator import validate_pdf_bytes, PDFValidationError

ALLOWED_HOSTS = {"dotic.ir", "www.dotic.ir"}

class PilotIntakeError(ValueError):
    pass

def _read_json(path: str | Path) -> dict:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        raise PilotIntakeError(f"گزارش پیش‌نیاز قابل خواندن نیست: {path}") from exc
    if not isinstance(value, dict):
        raise PilotIntakeError("ساختار گزارش پیش‌نیاز معتبر نیست")
    return value

def verify_readiness(network_report: dict, source_report: dict) -> None:
    if network_report.get("phase") != "10.4.2":
        raise PilotIntakeError("گزارش شبکه مربوط به فاز ۱۰.۴.۲ نیست")
    rows = [r for r in network_report.get("sources", []) if r.get("source_id") == "dotic"]
    if len(rows) != 1 or rows[0].get("status") != "tls_ok_http_not_tested":
        raise PilotIntakeError("DNS/TLS منبع Dotic در محیط استقرار تأیید نشده است")
    if source_report.get("phase") != "10.4.3":
        raise PilotIntakeError("گزارش منبع مربوط به فاز ۱۰.۴.۳ نیست")
    source = source_report.get("source", {})
    if source.get("robots_status") not in {"read", "not_found"}:
        raise PilotIntakeError("وضعیت robots.txt قابل تأیید نیست")
    if source.get("page_status") != "ok":
        raise PilotIntakeError("دسترسی به صفحه عمومی نمونه Dotic تأیید نشده است")

def intake_one_pdf(pdf_path: str | Path, source_url: str, quarantine_dir: str | Path,
                   network_report: dict, source_report: dict) -> dict:
    verify_readiness(network_report, source_report)
    parsed = urlparse(source_url)
    if (parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS or
            parsed.username or parsed.password or parsed.port not in (None, 443)):
        raise PilotIntakeError("نشانی سند باید HTTPS و متعلق به میزبان مجاز Dotic باشد")
    path = Path(pdf_path)
    data = path.read_bytes()
    validation = validate_pdf_bytes(data, source_url)
    digest = hashlib.sha256(data).hexdigest()
    root = Path(quarantine_dir)
    root.mkdir(parents=True, exist_ok=True)
    stored = root / f"{digest}.pdf"
    if stored.exists() and stored.read_bytes() != data:
        raise PilotIntakeError("تعارض هش؛ فایل موجود با محتوای ورودی یکسان نیست")
    if not stored.exists():
        stored.write_bytes(data)
    manifest = {
        "phase": "10.4.6", "pilot_type": "single_operator_supplied_pdf_no_network_fetch",
        "source_url": source_url, "original_filename": path.name,
        "stored_original": str(stored), "sha256": digest,
        "size_bytes": len(data), "page_count": validation["page_count"],
        "received_at": datetime.now(timezone.utc).isoformat(),
        "technical_validation": "passed", "legal_authenticity_verified": False,
        "legal_status_verified": False, "active_bank_write": False,
        "staging_registry_write": False,
        "decision": "quarantined_candidate_manual_provenance_and_legal_review_required"
    }
    manifest_path = root / f"{digest}.manifest.json"
    temp = manifest_path.with_suffix(".tmp")
    temp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(manifest_path)
    return manifest

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="One-document offline Dotic pilot intake")
    ap.add_argument("--pdf-file", required=True)
    ap.add_argument("--source-url", required=True)
    ap.add_argument("--network-report", required=True)
    ap.add_argument("--source-report", required=True)
    ap.add_argument("--quarantine-dir", default="/data/ingestion_quarantine/dotic_pilot")
    args = ap.parse_args(argv)
    report = intake_one_pdf(args.pdf_file, args.source_url, args.quarantine_dir,
                             _read_json(args.network_report), _read_json(args.source_report))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
