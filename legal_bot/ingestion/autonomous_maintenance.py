# -*- coding: utf-8 -*-
"""Autonomous, bounded legal-corpus maintenance (v1).

This module validates and stages candidate updates as guarded dry-run
transactions. It never writes active legal banks. A separate transaction
commit requires explicit human approval. Uncertain documents are rejected or
deferred; legal effect is never inferred from silence.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = "10.2"
MAX_PAGES_PER_RUN = 20
MAX_CANDIDATES_PER_RUN = 100
SUPPORTED_KINDS = {
    "law", "regulation", "supreme_court_ruling", "administrative_court_ruling",
    "advisory_opinion",
}
TARGETS = {
    "law": "laws.json",
    "regulation": "samples_and_circulars.json",
    "supreme_court_ruling": "rulings.json",
    "administrative_court_ruling": "rulings.json",
    "advisory_opinion": "consultations.json",
}


@dataclass(frozen=True)
class MaintenancePolicy:
    interval_days: int = 14
    max_pages_per_run: int = MAX_PAGES_PER_RUN
    max_candidates_per_run: int = MAX_CANDIDATES_PER_RUN
    include_historical_backfill: bool = True
    include_recent_updates: bool = True
    # Deprecated compatibility flag: active-bank writes are never performed here.
    automatic_active_bank_append: bool = False
    require_official_primary_source: bool = True
    require_official_status_evidence_for_norms: bool = True

    def validate(self) -> None:
        if self.interval_days < 1:
            raise ValueError("interval_days_must_be_positive")
        if not 1 <= self.max_pages_per_run <= MAX_PAGES_PER_RUN:
            raise ValueError("max_pages_per_run_must_be_between_1_and_20")
        if not 1 <= self.max_candidates_per_run <= MAX_CANDIDATES_PER_RUN:
            raise ValueError("max_candidates_per_run_must_be_between_1_and_100")


def schedule_config() -> dict[str, Any]:
    """Every other Monday at 09:00 Asia/Tehran; first run is an operator-set date."""
    return {
        "schema_version": SCHEMA_VERSION,
        "enabled": False,
        "timezone": "Asia/Tehran",
        "weekday": "MO",
        "interval_weeks": 2,
        "local_time": "09:00",
        "max_total_pdf_pages": MAX_PAGES_PER_RUN,
        "max_candidates": MAX_CANDIDATES_PER_RUN,
        "include_recent_and_historical": True,
        "last_successful_run": None,
        "next_run_at": None,
        "activation_note": "Enable only after verified official source adapters and host runtime connectivity are configured.",
    }


def _sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _norm(value: Any) -> str:
    s = str(value or "").strip()
    s = s.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    return re.sub(r"\s+", " ", s).casefold()


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
            f.write("\n"); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _validate_evidence(candidate: Mapping[str, Any], registry: Any) -> None:
    kind = candidate.get("document_kind")
    if kind not in SUPPORTED_KINDS:
        raise ValueError("unsupported_document_kind")
    if candidate.get("official_publication_verified") is not True:
        raise ValueError("official_publication_not_verified")
    source_id = str(candidate.get("source_id") or "")
    source = registry.get(source_id) if registry else None
    if source is None or source.authority_level != "official_primary" or source.status != "verified":
        raise ValueError("source_not_verified_official_primary")
    url = candidate.get("source_url")
    if not isinstance(url, str) or not source.permits_url(url):
        raise ValueError("source_url_not_permitted")
    evidence = candidate.get("publication_evidence")
    if not isinstance(evidence, Mapping) or not evidence.get("reference") or not re.fullmatch(r"[a-f0-9]{64}", str(evidence.get("sha256", ""))):
        raise ValueError("publication_evidence_incomplete")
    if kind in {"law", "regulation"}:
        status = candidate.get("legal_status")
        status_evidence = candidate.get("legal_status_evidence")
        if status != "in_force":
            raise ValueError("normative_status_not_confirmed_in_force")
        if not isinstance(status_evidence, Mapping) or status_evidence.get("official") is not True or not status_evidence.get("reference"):
            raise ValueError("official_current_status_evidence_missing")
    if kind in {"supreme_court_ruling", "administrative_court_ruling"}:
        if candidate.get("issuing_body_verified") is not True:
            raise ValueError("issuing_body_not_verified")
    if kind == "advisory_opinion" and candidate.get("issuing_body_verified") is not True:
        raise ValueError("advisory_opinion_issuer_not_verified")


def _map_record(candidate: Mapping[str, Any]) -> tuple[str, Any]:
    kind = candidate["document_kind"]
    title = str(candidate.get("title") or "").strip()
    if not title:
        raise ValueError("document_title_missing")
    common = {
        "منبع": candidate.get("source_url"),
        "شناسه_منبع": candidate.get("external_id"),
        "تاریخ": candidate.get("date"),
        "نوع سند": kind,
        "sha256": candidate.get("content_sha256"),
        "تعداد صفحات": candidate.get("page_count"),
    }
    if kind == "law":
        articles = candidate.get("articles")
        if not isinstance(articles, list) or not articles:
            raise ValueError("law_articles_missing")
        rows = []
        for article in articles:
            if not isinstance(article, Mapping) or not str(article.get("number", "")).strip() or not str(article.get("text", "")).strip():
                raise ValueError("law_article_invalid")
            rows.append({"ماده": str(article["number"]), "متن": str(article["text"]), "کلمات_کلیدی": [], "یادداشت": "افزوده‌شده با پایش خودکار؛ منبع و وضعیت اعتبار در فراداده سند ثبت شده است."})
        return TARGETS[kind], {"title": title, "rows": rows, "common": common}
    if kind in {"supreme_court_ruling", "administrative_court_ruling"}:
        text = str(candidate.get("text") or "").strip()
        if not text:
            raise ValueError("ruling_text_missing")
        row = {"نوع": "رأی وحدت رویه", "مرجع": candidate.get("issuer"), "شماره": candidate.get("number"), "تاریخ": candidate.get("date"), "عنوان": title, "متن": text, "منبع": candidate.get("source_url"), "شناسه_منبع": candidate.get("external_id"), "sha256": candidate.get("content_sha256")}
        return TARGETS[kind], {"list_key": "rulings" if kind == "supreme_court_ruling" else "diwan_adalat_rulings", "row": row}
    if kind == "advisory_opinion":
        question, opinion = str(candidate.get("question") or "").strip(), str(candidate.get("text") or "").strip()
        if not opinion:
            raise ValueError("consultation_text_missing")
        return TARGETS[kind], {"list_key": "consultations", "row": {"شماره": candidate.get("number"), "تاریخ": candidate.get("date"), "سؤال": question, "نظریه": opinion, "مرجع": candidate.get("issuer"), "منبع": candidate.get("source_url"), "شناسه_منبع": candidate.get("external_id"), "sha256": candidate.get("content_sha256")}}
    text = str(candidate.get("text") or "").strip()
    if not text:
        raise ValueError("regulation_text_missing")
    return TARGETS[kind], {"list_key": "circulars", "row": {"عنوان": title, "مرجع": candidate.get("issuer"), "موضوع": candidate.get("subject", ""), "متن": text, "تاریخ": candidate.get("date"), "منبع": candidate.get("source_url"), "شناسه_منبع": candidate.get("external_id"), "sha256": candidate.get("content_sha256")}}


def _append_to_bank(bank: Any, mapped: Any) -> bool:
    if "rows" in mapped:
        title = mapped["title"]
        rows = bank.setdefault(title, [])
        existing = {_norm(x.get("ماده")) for x in rows if isinstance(x, dict)}
        added = False
        for row in mapped["rows"]:
            if _norm(row["ماده"]) not in existing:
                rows.append(row); existing.add(_norm(row["ماده"])); added = True
        return added
    key, row = mapped["list_key"], mapped["row"]
    rows = bank.setdefault(key, [])
    stable = _norm(row.get("شناسه_منبع") or row.get("شماره") or row.get("عنوان"))
    for old in rows:
        if _norm(old.get("شناسه_منبع") or old.get("شماره") or old.get("عنوان")) == stable and stable:
            return False
    rows.append(row)
    return True


def run_autonomous_import(
    candidates: Iterable[Mapping[str, Any]], *, data_dir: str | Path,
    source_registry: Any, policy: MaintenancePolicy | None = None,
) -> dict[str, Any]:
    """Validate candidates and prepare a guarded dry-run bank transaction.

    Candidate acquisition/extraction adapters supply candidates. This function
    enforces the page budget and evidence gates, but never writes active banks.
    """
    policy = policy or MaintenancePolicy(); policy.validate()
    root = Path(data_dir)
    if not root.is_dir():
        raise FileNotFoundError("legal_data_directory_missing")
    report = {"schema_version": SCHEMA_VERSION, "started_at": datetime.now(timezone.utc).isoformat(), "processed": 0, "added": 0, "duplicates": 0, "rejected": [], "deferred": [], "active_bank_changed": False, "page_budget": policy.max_pages_per_run}
    page_total = 0
    staged: dict[str, Any] = {}
    expected_bank_hashes: dict[str, str] = {}
    for index, candidate in enumerate(candidates):
        if index >= policy.max_candidates_per_run:
            report["deferred"].append({"reason": "candidate_limit_reached"}); continue
        pages = candidate.get("page_count")
        if isinstance(pages, bool) or not isinstance(pages, int) or pages < 1:
            report["rejected"].append({"index": index, "reason": "page_count_invalid"}); continue
        if pages > policy.max_pages_per_run or page_total + pages > policy.max_pages_per_run:
            report["deferred"].append({"index": index, "reason": "20_page_run_budget_exceeded"}); continue
        page_total += pages; report["processed"] += 1
        try:
            _validate_evidence(candidate, source_registry)
            digest = str(candidate.get("content_sha256") or "")
            if not re.fullmatch(r"[a-f0-9]{64}", digest):
                raise ValueError("content_sha256_missing_or_invalid")
            target, mapped = _map_record(candidate)
            if target not in staged:
                active_raw = (root / target).read_bytes()
                expected_bank_hashes[target] = hashlib.sha256(active_raw).hexdigest()
                staged[target] = json.loads(active_raw.decode("utf-8"))
            if _append_to_bank(staged[target], mapped): report["added"] += 1
            else: report["duplicates"] += 1
        except Exception as exc:
            report["rejected"].append({"index": index, "reason": str(exc)})
    # Stage a transaction package only. This ingestion layer must never write
    # active legal banks directly, even if an old caller passes the deprecated
    # automatic_active_bank_append=True flag.
    if report["added"]:
        from .bank_transactions import prepare_transaction

        transaction_id = "auto-" + uuid.uuid4().hex
        prepared = prepare_transaction(
            staged, data_dir=root, transaction_id=transaction_id,
            expected_sha256=expected_bank_hashes,
        )
        report["transaction_id"] = transaction_id
        report["transaction_path"] = prepared["transaction_path"]
        report["transaction_status"] = prepared["status"]
        report["active_bank_changed"] = False
        report["commit_performed"] = False
        report["commit_reason"] = "explicit_human_approval_required"
    else:
        report["transaction_status"] = "not_required"
        report["commit_performed"] = False
    report["pages_used"] = page_total
    report["completed_at"] = datetime.now(timezone.utc).isoformat()
    report_path = root / "ingestion" / "autonomous_runs" / f"run_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}.json"
    _atomic_json(report_path, report)
    report["report_path"] = str(report_path)
    return report
