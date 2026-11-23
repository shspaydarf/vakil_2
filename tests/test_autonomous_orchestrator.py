import hashlib, json
from legal_bot.ingestion.autonomous_orchestrator import run_ingestion_cycle


def candidate(external="x", pages=2):
    return {"source_id":"official", "document_kind":"law", "issuer":"مجلس شورای اسلامی",
            "official_number":"123", "approval_date":"1400-01-01", "title":"قانون نمونه",
            "external_id":external, "page_count":pages, "content_sha256":hashlib.sha256(external.encode()).hexdigest()}


def adapters(accepted=True):
    def acquire(c): return {"page_count":c["page_count"], "local_path":"/tmp/fake.pdf"}
    def extract(c): return {"content_sha256":hashlib.sha256(c["external_id"].encode()).hexdigest(), "text":"متن"}
    def validate(c): return {"accepted":accepted, "primary_source_verified":accepted}
    return acquire, extract, validate


def test_orchestrator_runs_full_path_without_import_or_bank_write(tmp_path):
    a,e,v=adapters(); report=run_ingestion_cycle([candidate()], state_path=tmp_path/"state.json", acquire=a, extract=e, validate=v)
    assert report["processed"] == 1 and report["imported"] == 0 and report["import_enabled"] is False
    assert report["items"][0]["state"] == "ready_for_import"


def test_orchestrator_remembers_same_document_version(tmp_path):
    a,e,v=adapters(); path=tmp_path/"state.json"
    run_ingestion_cycle([candidate()], state_path=path, acquire=a, extract=e, validate=v)
    second=run_ingestion_cycle([candidate()], state_path=path, acquire=a, extract=e, validate=v)
    assert second["duplicates"] == 1 and second["processed"] == 0


def test_orchestrator_quarantines_unverified_document(tmp_path):
    a,e,v=adapters(False); report=run_ingestion_cycle([candidate()], state_path=tmp_path/"state.json", acquire=a, extract=e, validate=v)
    assert report["quarantined"] == 1 and report["imported"] == 0


def test_orchestrator_respects_cumulative_page_budget(tmp_path):
    a,e,v=adapters(); report=run_ingestion_cycle([candidate("a",12),candidate("b",9)], state_path=tmp_path/"state.json", acquire=a, extract=e, validate=v)
    assert report["pages_used"] == 12 and report["processed"] == 1 and report["deferred"] == 1


def test_orchestrator_import_requires_explicit_adapter(tmp_path):
    a,e,v=adapters(); calls=[]
    def importer(c): calls.append(c); return {"imported":True}
    report=run_ingestion_cycle([candidate()], state_path=tmp_path/"state.json", acquire=a, extract=e, validate=v, import_document=importer)
    assert report["imported"] == 1 and calls and report["items"][0]["state"] == "imported"
