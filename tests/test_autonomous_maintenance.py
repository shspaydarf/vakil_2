import hashlib, json
from pathlib import Path
from types import SimpleNamespace
import pytest
from legal_bot.ingestion.autonomous_maintenance import (
    MaintenancePolicy, run_autonomous_import, schedule_config,
)

class Registry:
    def get(self, source_id):
        if source_id != "official": return None
        return SimpleNamespace(authority_level="official_primary", status="verified",
                               permits_url=lambda u: u == "https://official.example/law/1")

def _candidate(**extra):
    digest = hashlib.sha256(b"verified document").hexdigest()
    return {
        "document_kind": "law", "source_id": "official",
        "source_url": "https://official.example/law/1", "official_publication_verified": True,
        "publication_evidence": {"reference": "official-record-1", "sha256": digest},
        "legal_status": "in_force", "legal_status_evidence": {"official": True, "reference": "status-record-1"},
        "content_sha256": digest, "page_count": 2, "title": "قانون آزمایشی",
        "external_id": "law-1", "articles": [{"number": "1", "text": "متن ماده یک"}], **extra
    }

def _banks(root):
    (root/"laws.json").write_text("{}", encoding="utf-8")
    (root/"rulings.json").write_text(json.dumps({"metadata":{},"rulings":[],"diwan_adalat_rulings":[]}), encoding="utf-8")
    (root/"consultations.json").write_text(json.dumps({"metadata":{},"consultations":[]}), encoding="utf-8")
    (root/"samples_and_circulars.json").write_text(json.dumps({"metadata":{},"samples":[],"circulars":[]}), encoding="utf-8")

def test_schedule_is_biweekly_monday_tehran_and_disabled_until_configured():
    cfg = schedule_config()
    assert cfg["interval_weeks"] == 2 and cfg["weekday"] == "MO"
    assert cfg["timezone"] == "Asia/Tehran" and cfg["enabled"] is False
    assert cfg["max_total_pdf_pages"] == 20

def test_verified_law_prepares_transaction_without_writing_active_bank(tmp_path):
    _banks(tmp_path)
    before = {name: (tmp_path/name).read_bytes() for name in
              ("laws.json", "rulings.json", "consultations.json", "samples_and_circulars.json")}
    result = run_autonomous_import([_candidate()], data_dir=tmp_path, source_registry=Registry())
    assert result["added"] == 1 and result["active_bank_changed"] is False
    assert result["commit_performed"] is False
    assert result["transaction_status"] == "prepared_dry_run"
    manifest = json.loads((Path(result["transaction_path"])/"transaction_manifest.json").read_text())
    assert manifest["status"] == "prepared_dry_run"
    assert manifest["active_bank_modified"] is False
    assert all((tmp_path/name).read_bytes() == raw for name, raw in before.items())


def test_legacy_auto_append_flag_cannot_bypass_transaction_gate(tmp_path):
    _banks(tmp_path)
    before = (tmp_path/"laws.json").read_bytes()
    result = run_autonomous_import([_candidate()], data_dir=tmp_path, source_registry=Registry(),
                                   policy=MaintenancePolicy(automatic_active_bank_append=True))
    assert result["added"] == 1 and result["active_bank_changed"] is False
    assert (tmp_path/"laws.json").read_bytes() == before



def test_stale_bank_snapshot_is_rejected_before_transaction_preparation(tmp_path, monkeypatch):
    import legal_bot.ingestion.bank_transactions as transactions

    _banks(tmp_path)
    original_prepare = transactions.prepare_transaction

    def mutate_then_prepare(replacements, **kwargs):
        (tmp_path/"laws.json").write_text('{"external_edit": true}', encoding="utf-8")
        return original_prepare(replacements, **kwargs)

    monkeypatch.setattr(transactions, "prepare_transaction", mutate_then_prepare)
    with pytest.raises(RuntimeError, match="concurrency_conflict:laws.json"):
        run_autonomous_import([_candidate()], data_dir=tmp_path, source_registry=Registry())
    assert json.loads((tmp_path/"laws.json").read_text(encoding="utf-8")) == {"external_edit": True}

def test_repealed_or_unknown_law_is_not_added(tmp_path):
    _banks(tmp_path)
    result = run_autonomous_import([_candidate(legal_status="unknown")], data_dir=tmp_path, source_registry=Registry())
    assert result["added"] == 0 and result["active_bank_changed"] is False
    assert result["rejected"][0]["reason"] == "normative_status_not_confirmed_in_force"

def test_twenty_page_total_budget_defers_overflow(tmp_path):
    _banks(tmp_path)
    a, b = _candidate(page_count=12), _candidate(page_count=9, external_id="law-2")
    result = run_autonomous_import([a,b], data_dir=tmp_path, source_registry=Registry())
    assert result["pages_used"] == 12
    assert result["added"] == 1 and result["deferred"][0]["reason"] == "20_page_run_budget_exceeded"
    assert result["active_bank_changed"] is False

def test_unverified_secondary_source_never_enters_active_bank(tmp_path):
    _banks(tmp_path)
    c = _candidate(source_id="secondary", source_url="https://secondary.example/law/1")
    result = run_autonomous_import([c], data_dir=tmp_path, source_registry=Registry())
    assert result["added"] == 0 and not result["active_bank_changed"]

@pytest.mark.parametrize("kind,extra,target,key", [
    ("regulation", {"text":"متن آیین‌نامه"}, "samples_and_circulars.json", "circulars"),
    ("supreme_court_ruling", {"text":"متن رأی", "issuer":"هیأت عمومی دیوان عالی کشور", "issuing_body_verified":True}, "rulings.json", "rulings"),
    ("administrative_court_ruling", {"text":"متن رأی", "issuer":"هیأت عمومی دیوان عدالت اداری", "issuing_body_verified":True}, "rulings.json", "diwan_adalat_rulings"),
    ("advisory_opinion", {"text":"متن نظریه", "question":"سؤال", "issuer":"اداره کل حقوقی قوه قضاییه", "issuing_body_verified":True}, "consultations.json", "consultations"),
])
def test_non_law_document_families_are_routed_to_their_json_banks(tmp_path, kind, extra, target, key):
    _banks(tmp_path)
    c = _candidate(document_kind=kind, legal_status=("in_force" if kind == "regulation" else None), legal_status_evidence=({"official":True,"reference":"status-record-1"} if kind == "regulation" else None), articles=None, **extra)
    result = run_autonomous_import([c], data_dir=tmp_path, source_registry=Registry())
    assert result["added"] == 1
    assert result["active_bank_changed"] is False
    manifest = json.loads((Path(result["transaction_path"])/"transaction_manifest.json").read_text())
    assert [op["target"] for op in manifest["operations"]] == [target]
    assert manifest["active_bank_modified"] is False
