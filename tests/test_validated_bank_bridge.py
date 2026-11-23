import hashlib, json
from types import SimpleNamespace
from legal_bot.ingestion.validated_bank_bridge import run_validated_bank_bridge

class Registry:
    def get(self, source_id):
        if source_id != "official": return None
        return SimpleNamespace(authority_level="official_primary", status="verified",
                               permits_url=lambda u: u == "https://official.example/law/1")

def _candidate():
    digest = hashlib.sha256(b"doc").hexdigest()
    return {"document_kind":"law", "source_id":"official", "source_url":"https://official.example/law/1",
            "official_publication_verified":True, "publication_evidence":{"reference":"pub-1","sha256":digest},
            "legal_status":"in_force", "legal_status_evidence":{"official":True,"reference":"status-1"},
            "content_sha256":digest, "page_count":1, "title":"قانون آزمایشی",
            "external_id":"law-1", "articles":[{"number":"1","text":"متن ماده"}]}

def _attestation():
    return {"provenance":{"origin_consistency":"consistent_with_catalog","eligible_for_next_review":True,"document_authenticity":"not_proven","findings":[]},
            "metadata":{"overall_status":"screening_passed","findings":[]},
            "completeness":{"status":"screening_no_anomaly_detected","findings":[]},
            "version_conflict":{"status":"no_conflict_detected","comparisons":[],"findings":[]},
            "source_match":{"status":"official_source_match_candidate","official_confirmation":False,"findings":[]}}

def _banks(root):
    (root/"laws.json").write_text("{}", encoding="utf-8")
    (root/"rulings.json").write_text(json.dumps({"metadata":{},"rulings":[],"diwan_adalat_rulings":[]}), encoding="utf-8")
    (root/"consultations.json").write_text(json.dumps({"metadata":{},"consultations":[]}), encoding="utf-8")
    (root/"samples_and_circulars.json").write_text(json.dumps({"metadata":{},"samples":[],"circulars":[]}), encoding="utf-8")

def test_complete_machine_attestation_prepares_transaction_without_active_write(tmp_path):
    _banks(tmp_path)
    before = (tmp_path/"laws.json").read_bytes()
    result = run_validated_bank_bridge([{"candidate":_candidate(),"validation_attestation":_attestation()}],
                                       data_dir=str(tmp_path), source_registry=Registry())
    assert result["added"] == 1 and result["active_bank_changed"] is False
    assert result["commit_performed"] is False
    assert result["official_authenticity_proven"] is False and result["legal_validity_proven"] is False
    assert (tmp_path/"laws.json").read_bytes() == before
    assert result["transaction_status"] == "prepared_dry_run"

def test_missing_attestation_fails_closed_and_preserves_banks(tmp_path):
    _banks(tmp_path); before=(tmp_path/"laws.json").read_bytes()
    result = run_validated_bank_bridge([{"candidate":_candidate(),"validation_attestation":{}}],
                                       data_dir=str(tmp_path), source_registry=Registry())
    assert result["added"] == 0 and not result["active_bank_changed"]
    assert (tmp_path/"laws.json").read_bytes() == before

def test_medium_version_finding_blocks_append(tmp_path):
    _banks(tmp_path); att=_attestation()
    att["version_conflict"]["comparisons"]=[{"document_id":"old"}]
    result = run_validated_bank_bridge([{"candidate":_candidate(),"validation_attestation":att}],
                                       data_dir=str(tmp_path), source_registry=Registry())
    assert result["added"] == 0 and not result["active_bank_changed"]
    assert "version_conflict_requires_review" in result["rejected_by_validation_gate"][0]["reason"]

def test_secondary_source_still_rejected_after_screening(tmp_path):
    _banks(tmp_path); candidate=_candidate(); candidate["source_id"]="secondary"
    result = run_validated_bank_bridge([{"candidate":candidate,"validation_attestation":_attestation()}],
                                       data_dir=str(tmp_path), source_registry=Registry())
    assert result["added"] == 0 and not result["active_bank_changed"]
