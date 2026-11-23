# -*- coding: utf-8 -*-
"""Phase 10.1.3 synthetic integration tests; no network or production-bank writes."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from legal_bot.ingestion.pipeline_contracts import (
    make_envelope, stable_document_key, transition, version_key,
)
from legal_bot.ingestion.autonomous_maintenance import (
    MaintenancePolicy, run_autonomous_import,
)


class _Source:
    authority_level = "official_primary"
    status = "verified"

    def permits_url(self, url: str) -> bool:
        return url == "https://official.example.test/law/42"


class _Registry:
    def get(self, source_id: str):
        return _Source() if source_id == "official_test" else None


def _candidate(*, pages=2, external_id="law-42", digest=None):
    digest = digest or hashlib.sha256(b"synthetic legal text").hexdigest()
    return {
        "document_kind": "law", "source_id": "official_test",
        "source_url": "https://official.example.test/law/42",
        "external_id": external_id, "title": "قانون آزمایشی برای آزمون",
        "date": "1405/01/01", "number": "42", "issuer": "مجلس شورای اسلامی",
        "page_count": pages, "content_sha256": digest,
        "official_publication_verified": True,
        "publication_evidence": {"reference": "official-record-42", "sha256": "a" * 64},
        "legal_status": "in_force",
        "legal_status_evidence": {"official": True, "reference": "official-current-status"},
        "articles": [{"number": "1", "text": "متن آزمایشی ماده اول"}],
    }


def test_synthetic_document_crosses_contract_lifecycle_and_identity():
    doc = {"document_kind": "law", "issuer": "مجلس شورای اسلامی", "official_number": "۴۲", "approval_date": "۱۴۰۵/۰۱/۰۱"}
    document_id = stable_document_key(doc)
    envelope = make_envelope(
        source_id="official_test", document_kind="law", title="قانون آزمایشی",
        document_id=document_id, source_url="https://official.example.test/law/42",
    )
    states = ["identity_checked", "queued", "acquired", "extracted", "validated", "ready_for_import", "imported"]
    for state in states:
        envelope = transition(envelope, state)
    assert envelope["state"] == "imported"
    assert stable_document_key({**doc, "issuer": "مجلس شورای اسلامی"}) == document_id
    assert version_key(document_id, hashlib.sha256(b"v1").hexdigest()) != version_key(document_id, hashlib.sha256(b"v2").hexdigest())


def test_synthetic_import_prepares_transaction_and_never_writes_active_bank(tmp_path: Path):
    (tmp_path / "laws.json").write_text("{}", encoding="utf-8")
    candidate = _candidate()
    before = (tmp_path / "laws.json").read_bytes()
    # Even a legacy caller explicitly passing True cannot trigger a direct write.
    policy = MaintenancePolicy(max_pages_per_run=20, automatic_active_bank_append=True)
    first = run_autonomous_import([candidate], data_dir=tmp_path, source_registry=_Registry(), policy=policy)
    assert first["added"] == 1 and first["active_bank_changed"] is False
    assert first["transaction_status"] == "prepared_dry_run"
    assert (tmp_path / "laws.json").read_bytes() == before
    manifest = json.loads((Path(first["transaction_path"]) / "transaction_manifest.json").read_text())
    assert manifest["status"] == "prepared_dry_run"
    assert manifest["operations"][0]["target"] == "laws.json"


def test_synthetic_run_respects_cumulative_twenty_page_budget_and_defers(tmp_path: Path):
    (tmp_path / "laws.json").write_text("{}", encoding="utf-8")
    candidates = [_candidate(pages=12, external_id="law-12"), _candidate(pages=9, external_id="law-9")]
    report = run_autonomous_import(
        candidates, data_dir=tmp_path, source_registry=_Registry(),
        policy=MaintenancePolicy(max_pages_per_run=20, automatic_active_bank_append=False),
    )
    assert report["processed"] == 1
    assert report["pages_used"] == 12
    assert report["deferred"] == [{"index": 1, "reason": "20_page_run_budget_exceeded"}]
    assert report["active_bank_changed"] is False
    assert json.loads((tmp_path / "laws.json").read_text(encoding="utf-8")) == {}


def test_synthetic_import_rejects_unverified_current_status(tmp_path: Path):
    (tmp_path / "laws.json").write_text("{}", encoding="utf-8")
    candidate = _candidate()
    candidate["legal_status"] = "unknown"
    report = run_autonomous_import([candidate], data_dir=tmp_path, source_registry=_Registry())
    assert report["added"] == 0
    assert report["rejected"][0]["reason"] == "normative_status_not_confirmed_in_force"
    assert json.loads((tmp_path / "laws.json").read_text(encoding="utf-8")) == {}


def test_synthetic_import_rejects_non_allowlisted_source_url(tmp_path: Path):
    (tmp_path / "laws.json").write_text("{}", encoding="utf-8")
    candidate = _candidate()
    candidate["source_url"] = "https://untrusted.example.test/law/42"
    report = run_autonomous_import([candidate], data_dir=tmp_path, source_registry=_Registry())
    assert report["added"] == 0
    assert report["rejected"][0]["reason"] == "source_url_not_permitted"
