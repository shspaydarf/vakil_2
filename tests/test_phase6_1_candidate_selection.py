import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "legal_bot/data/iran/ingestion/test_candidates/phase6_1_candidate.json"


def load_candidate():
    return json.loads(CANDIDATE.read_text(encoding="utf-8"))


def test_candidate_is_selected_but_not_approved_for_ingestion():
    candidate = load_candidate()
    decision = candidate["phase6_1_decision"]
    assert decision["selected_for_next_phase"] is True
    assert decision["approved_for_ingestion"] is False
    assert decision["approved_for_active_bank"] is False


def test_mirror_is_explicitly_not_an_official_ingestion_source():
    candidate = load_candidate()
    mirror = candidate["sources"]["discovery_mirror"]
    assert mirror["is_official_source_for_ingestion"] is False
    assert "rc.majlis.ir" in candidate["sources"]["preferred_official_source"]["url"]
    assert candidate["sources"]["preferred_official_source"]["is_official_pdf_download_confirmed"] is False


def test_candidate_is_not_misrepresented_as_downloaded_or_fingerprinted():
    candidate = load_candidate()
    risks = " ".join(candidate["known_risks_and_open_checks"])
    assert "No PDF was downloaded" in risks
    assert candidate["candidate_status"] == "selected_pending_official_pdf_acquisition"
